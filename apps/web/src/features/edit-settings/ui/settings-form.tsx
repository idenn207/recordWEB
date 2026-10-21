import { Tab, TabGroup, TabList, TabPanel, TabPanels } from '@headlessui/react';
import { useEffect, useState } from 'react';
import { type Config, type Secrets, testTelegram, useSaveConfig, useSaveSecrets } from '@/entities/config';
import { cn } from '@/shared/lib/cn';
import { Button, Field, Notice, Select, TextArea, TextInput, ToggleRow, useToast } from '@/shared/ui';

const TABS = ['녹화', '후처리', '파일 관리자', '계정·알림'] as const;

const Section = ({ children }: { children: React.ReactNode }) => <div className="grid max-w-2xl gap-4 py-4">{children}</div>;

export function SettingsForm({ config, secrets }: { config: Config; secrets: Secrets }) {
  const [cfg, setCfg] = useState(config);
  const [sec, setSec] = useState(secrets);
  const saveConfig = useSaveConfig();
  const saveSecrets = useSaveSecrets();
  const toast = useToast();
  useEffect(() => setCfg(config), [config]);
  useEffect(() => setSec(secrets), [secrets]);

  const set = <K extends keyof Config>(k: K, v: Config[K]) => setCfg((c) => ({ ...c, [k]: v }));
  const dirty = JSON.stringify(cfg) !== JSON.stringify(config) || JSON.stringify(sec) !== JSON.stringify(secrets);

  const save = async () => {
    try {
      await saveConfig.mutateAsync(cfg);
      await saveSecrets.mutateAsync(sec);
      toast('저장했습니다');
    } catch (e) {
      toast((e as Error).message, 'error');
    }
  };

  const text = (k: keyof Config, label: string, hint?: string, mono = false) => (
    <Field label={label} hint={hint}>
      {(id) => <TextInput id={id} value={String(cfg[k] ?? '')} onChange={(e) => set(k, e.target.value as never)} className={cn(mono && 'font-mono text-[0.85rem]')} />}
    </Field>
  );

  return (
    <TabGroup>
      <TabList className="flex flex-wrap gap-1 border-b border-line">
        {TABS.map((t) => (
          <Tab key={t} className="-mb-px rounded-t-lg border border-transparent px-3.5 py-2 font-semibold text-muted data-[selected]:border-line data-[selected]:border-b-bg data-[selected]:bg-bg data-[selected]:text-ink data-[hover]:text-ink">
            {t}
          </Tab>
        ))}
      </TabList>
      <TabPanels>
        <TabPanel>
          <Section>
            <ToggleRow label="자동 녹화 모드" hint="서버가 시작될 때 자동 녹화가 켜진 채널의 감시를 바로 시작합니다" checked={cfg.autoRecordingMode} onChange={(v) => set('autoRecordingMode', v)} />
            <Field label="재탐색 주기 (초)" hint="방송이 꺼져 있을 때 켜졌는지 확인하는 간격. 10초 이상">
              {(id) => <TextInput id={id} type="number" min={10} value={cfg.recheckInterval} onChange={(e) => set('recheckInterval', Number(e.target.value))} />}
            </Field>
            {text('filenamePattern', '파일명 패턴', '{start_time} {recording_time} {channel_name} {safe_live_title} {record_quality} {frame_rate} {file_extension}', true)}
          </Section>
        </TabPanel>

        <TabPanel>
          <Section>
            <ToggleRow label="녹화 후 자동 후처리" hint="녹화가 끝나면 fixed_ 파일을 만들어 재생 문제를 줄입니다" checked={cfg.autoPostProcessing} onChange={(v) => set('autoPostProcessing', v)} />
            <ToggleRow label="후처리 후 원본 삭제" checked={cfg.deleteAfterPostProcessing} onChange={(v) => set('deleteAfterPostProcessing', v)} />
            <ToggleRow label="fixed_ 접두사 제거" hint="원본을 지우지 않았고 같은 이름이 있으면 접두사를 유지합니다" checked={cfg.removeFixedPrefix} onChange={(v) => set('removeFixedPrefix', v)} />
            <ToggleRow label="후처리 후 다른 폴더로 이동" checked={cfg.moveAfterProcessingEnabled} onChange={(v) => set('moveAfterProcessingEnabled', v)} />
            {cfg.moveAfterProcessingEnabled && text('moveAfterProcessing', '이동할 폴더', undefined, true)}
            <ToggleRow label="스트림 복사 (재인코딩 안 함)" hint="끄면 아래 설정으로 영상을 다시 인코딩합니다. CPU를 많이 씁니다" checked={cfg.stream_copy} onChange={(v) => set('stream_copy', v)} />
            {!cfg.stream_copy && (
              <div className="grid gap-4 border-t border-line pt-4 sm:grid-cols-2">
                <Field label="영상 코덱">
                  {(id) => (
                    <Select id={id} value={cfg.video_codec} onChange={(e) => set('video_codec', e.target.value)}>
                      <option>libx264</option>
                      <option>libx265</option>
                    </Select>
                  )}
                </Field>
                <Field label="프리셋">
                  {(id) => (
                    <Select id={id} value={cfg.preset} onChange={(e) => set('preset', e.target.value)}>
                      {['ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow'].map((p) => (
                        <option key={p}>{p}</option>
                      ))}
                    </Select>
                  )}
                </Field>
                <Field label="출력 해상도" hint="원본보다 크게 만들지 않습니다">
                  {(id) => (
                    <Select id={id} value={cfg.postprocess_resolution} onChange={(e) => set('postprocess_resolution', e.target.value as Config['postprocess_resolution'])}>
                      <option value="source">원본</option>
                      <option value="1080p">1080p</option>
                      <option value="720p">720p</option>
                      <option value="480p">480p</option>
                    </Select>
                  )}
                </Field>
                <div className="flex items-end">
                  <ToggleRow label="비트레이트 모드" hint="끄면 CRF(화질) 모드" checked={cfg.use_bitrate_mode} onChange={(v) => set('use_bitrate_mode', v)} />
                </div>
                {cfg.use_bitrate_mode ? (
                  <>
                    {text('video_bitrate', '영상 비트레이트', '예: 8000k')}
                    {text('vbv_maxrate', '최대 비트레이트 (선택)')}
                    {text('vbv_bufsize', '버퍼 크기 (선택)')}
                  </>
                ) : (
                  <Field label="CRF (낮을수록 고화질)">{(id) => <TextInput id={id} type="number" min={0} max={51} value={cfg.video_quality} onChange={(e) => set('video_quality', Number(e.target.value))} />}</Field>
                )}
                {text('audio_codec', '오디오 코덱')}
                {text('audio_bitrate', '오디오 비트레이트', 'copy를 쓰면 그대로 복사')}
                <div className="sm:col-span-2">{text('extra_ffmpeg_options', 'ffmpeg 추가 옵션', '-vf를 넣으면 위의 해상도 설정은 무시됩니다', true)}</div>
              </div>
            )}
          </Section>
        </TabPanel>

        <TabPanel>
          <Section>
            <ToggleRow label="파일 관리자 사용" checked={cfg.fileManagerEnabled} onChange={(v) => set('fileManagerEnabled', v)} />
            {cfg.fileManagerEnabled && cfg.fileManagerMode === 'blacklist' && <Notice tone="warn">제한 없는 모드에서는 같은 네트워크의 누구나 시스템 폴더를 제외한 모든 파일을 지울 수 있습니다. 접근 통제는 네트워크 경계뿐입니다.</Notice>}
            <Field label="접근 범위">
              {(id) => (
                <Select id={id} value={cfg.fileManagerMode} onChange={(e) => set('fileManagerMode', e.target.value as Config['fileManagerMode'])}>
                  <option value="blacklist">제한 없음 (시스템 폴더만 차단)</option>
                  <option value="whitelist">허용한 폴더만</option>
                </Select>
              )}
            </Field>
            {cfg.fileManagerMode === 'whitelist' && (
              <Field label="추가로 허용할 폴더" hint="한 줄에 하나. 채널 저장 폴더와 이동 폴더는 자동으로 허용됩니다">
                {(id) => <TextArea id={id} rows={3} value={cfg.fileManagerRoots.join('\n')} onChange={(e) => set('fileManagerRoots', e.target.value.split('\n').map((l) => l.trim()).filter(Boolean))} />}
              </Field>
            )}
            <ToggleRow label="읽기 전용" hint="이동·삭제·이름 변경을 막습니다" checked={cfg.fileManagerReadOnly} onChange={(v) => set('fileManagerReadOnly', v)} />
            <ToggleRow label="휴지통 사용" hint="삭제할 때 .trash 폴더로 옮깁니다" checked={cfg.trashEnabled} onChange={(v) => set('trashEnabled', v)} />
          </Section>
        </TabPanel>

        <TabPanel>
          <Section>
            <p className="font-bold">치지직 로그인 쿠키</p>
            <p className="-mt-3 text-[0.8rem] text-muted">성인 방송이나 로그인이 필요한 방송을 녹화할 때만 필요합니다</p>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="NID_AUT">{(id) => <TextInput id={id} value={sec.chzzk.NID_AUT ?? ''} onChange={(e) => setSec({ ...sec, chzzk: { ...sec.chzzk, NID_AUT: e.target.value } })} autoComplete="off" className="font-mono text-[0.85rem]" />}</Field>
              <Field label="NID_SES">{(id) => <TextInput id={id} value={sec.chzzk.NID_SES ?? ''} onChange={(e) => setSec({ ...sec, chzzk: { ...sec.chzzk, NID_SES: e.target.value } })} autoComplete="off" className="font-mono text-[0.85rem]" />}</Field>
            </div>
            <Field label="유튜브 쿠키 (Netscape 형식)" hint="비워 두면 공개 라이브만 녹화합니다">
              {(id) => <TextArea id={id} rows={4} value={sec.youtubeCookie} onChange={(e) => setSec({ ...sec, youtubeCookie: e.target.value })} spellCheck={false} />}
            </Field>
            {text('ytPoToken', '유튜브 PO 토큰', '여러 개는 쉼표로 구분. 접두사가 없으면 mweb.gvs로 처리합니다', true)}

            <p className="mt-2 font-bold">텔레그램 알림</p>
            <ToggleRow label="알림 사용" hint="녹화 시작·종료를 텔레그램으로 알립니다" checked={cfg.telegram_enabled} onChange={(v) => set('telegram_enabled', v)} />
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="봇 토큰">{(id) => <TextInput id={id} value={sec.telegram.token} onChange={(e) => setSec({ ...sec, telegram: { ...sec.telegram, token: e.target.value } })} autoComplete="off" className="font-mono text-[0.85rem]" />}</Field>
              <Field label="채팅 ID">{(id) => <TextInput id={id} value={sec.telegram.chatId} onChange={(e) => setSec({ ...sec, telegram: { ...sec.telegram, chatId: e.target.value } })} className="font-mono text-[0.85rem]" />}</Field>
            </div>
            <div>
              <Button
                disabled={dirty}
                title={dirty ? '저장한 뒤에 테스트할 수 있습니다' : undefined}
                onClick={() => testTelegram().then(() => toast('테스트 메시지를 보냈습니다'), (e: Error) => toast(e.message, 'error'))}
              >
                테스트 메시지 보내기
              </Button>
            </div>
          </Section>
        </TabPanel>
      </TabPanels>

      <div className="sticky bottom-0 -mx-4 mt-2 flex items-center gap-3 border-t border-line bg-bg px-4 py-3 md:-mx-8 md:px-8">
        <Button variant="primary" onClick={save} disabled={!dirty || saveConfig.isPending || saveSecrets.isPending}>
          저장
        </Button>
        <span className="text-muted" role="status">
          {dirty ? '저장하지 않은 변경이 있습니다' : '변경 사항 없음'}
        </span>
      </div>
    </TabGroup>
  );
}
