import { Tabs } from "@base-ui/react/tabs";
import { useEffect, useState } from "react";
import {
  fetchSecrets,
  type Config,
  type Secrets,
  testTelegram,
  useSaveConfig,
  useSaveSecrets,
} from "@/entities/config";
import { XConnectCard } from "@/features/connect-x";
import { cn } from "@/shared/lib/cn";
import {
  Button,
  Card,
  Field,
  FloatingBar,
  Notice,
  Select,
  TextArea,
  TextInput,
  ToggleRow,
  useToast,
} from "@/shared/ui";

// 가려진 값(••••abcd)은 일부만 고칠 수 없다. 누르면 전체를 선택해 바로 새 값으로 덮어쓰게 한다.
const selectMasked = (
  e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>,
) => {
  if (e.target.value.startsWith("••••")) e.target.select();
};

const TABS = ["녹화", "후처리", "파일 관리자", "연동"] as const;

const TAB_CLASS =
  "-mb-px inline-flex h-11 items-center border-b-2 border-transparent px-4 text-base text-muted outline-none transition-colors hover:text-ink data-[active]:border-ink data-[active]:font-bold data-[active]:text-ink focus-visible:outline-2 focus-visible:outline-brand";

const Group = ({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) => (
  <Card className="grid content-start gap-4 p-5">
    <h2 className="text-base font-semibold">{title}</h2>
    {children}
  </Card>
);

const Section = ({ children }: { children: React.ReactNode }) => (
  <div className="grid items-start gap-6 py-5 lg:grid-cols-2">{children}</div>
);

export function SettingsForm({
  config,
  secrets,
}: {
  config: Config;
  secrets: Secrets;
}) {
  const [cfg, setCfg] = useState(config);
  const [sec, setSec] = useState(secrets);
  const saveConfig = useSaveConfig();
  const saveSecrets = useSaveSecrets();
  const toast = useToast();
  useEffect(() => setCfg(config), [config]);
  // X 카드는 자체 저장으로 secrets 를 다시 불러온다. 다른 칸의 미저장 입력은 덮어쓰지 않도록 X 값만 따라간다.
  useEffect(
    () => setSec((s) => ({ ...s, xCookie: secrets.xCookie })),
    [secrets.xCookie],
  );

  const set = <K extends keyof Config>(k: K, v: Config[K]) =>
    setCfg((c) => ({ ...c, [k]: v }));
  const dirty =
    JSON.stringify(cfg) !== JSON.stringify(config) ||
    JSON.stringify(sec) !== JSON.stringify(secrets);

  const pending = saveConfig.isPending || saveSecrets.isPending;

  const save = async () => {
    try {
      if (JSON.stringify(cfg) !== JSON.stringify(config))
        await saveConfig.mutateAsync(cfg);
      if (JSON.stringify(sec) !== JSON.stringify(secrets)) {
        await saveSecrets.mutateAsync(sec);
        setSec(await fetchSecrets()); // 서버가 돌려주는 가려진 값으로 입력창을 되돌린다(원문이 남지 않게)
      }
      toast("저장했습니다");
    } catch (e) {
      toast((e as Error).message, "error");
    }
  };

  const text = (
    k: keyof Config,
    label: string,
    hint?: string,
    mono = false,
  ) => (
    <Field label={label} hint={hint}>
      {(id) => (
        <TextInput
          id={id}
          value={String(cfg[k] ?? "")}
          onChange={(e) => set(k, e.target.value as never)}
          className={cn(mono && "font-mono text-[13px]")}
        />
      )}
    </Field>
  );

  return (
    <Tabs.Root defaultValue={location.hash === "#x" ? 3 : 0}>
      <Tabs.List className="flex flex-wrap gap-1 border-b border-line">
        {TABS.map((t, i) => (
          <Tabs.Tab key={t} value={i} className={TAB_CLASS}>
            {t}
          </Tabs.Tab>
        ))}
      </Tabs.List>
      <div>
        <Tabs.Panel value={0} keepMounted>
          <Section>
            <Group title="녹화">
              <ToggleRow
                label="자동 녹화 모드"

                checked={cfg.autoRecordingMode}
                onChange={(v) => set("autoRecordingMode", v)}
              />
              <Field label="방송 확인 주기 (초)">
                {(id) => (
                  <TextInput
                    id={id}
                    type="number"
                    min={10}
                    value={cfg.recheckInterval}
                    onChange={(e) =>
                      set("recheckInterval", Number(e.target.value))
                    }
                  />
                )}
              </Field>
            </Group>
            <Group title="파일명">
              {text(
                "filenamePattern",
                "파일명 패턴",
                "{start_time} {recording_time} {channel_name} {safe_live_title} {record_quality} {frame_rate} {file_extension}",
                true,
              )}
            </Group>
          </Section>
        </Tabs.Panel>

        <Tabs.Panel value={1} keepMounted>
          <Section>
            <Group title="후처리">
              <ToggleRow
                label="녹화 후 자동 후처리"

                checked={cfg.autoPostProcessing}
                onChange={(v) => set("autoPostProcessing", v)}
              />
              <ToggleRow
                label="후처리 후 원본 삭제"
                checked={cfg.deleteAfterPostProcessing}
                onChange={(v) => set("deleteAfterPostProcessing", v)}
              />
              <ToggleRow
                label="fixed_ 접두사 제거"

                checked={cfg.removeFixedPrefix}
                onChange={(v) => set("removeFixedPrefix", v)}
              />
              <ToggleRow
                label="후처리 후 다른 폴더로 이동"
                checked={cfg.moveAfterProcessingEnabled}
                onChange={(v) => set("moveAfterProcessingEnabled", v)}
              />
              {cfg.moveAfterProcessingEnabled &&
                text("moveAfterProcessing", "이동할 폴더", undefined, true)}
            </Group>
            <Group title="인코딩">
              <ToggleRow
                label="스트림 복사 (재인코딩 안 함)"
                hint="끄면 재인코딩하며 CPU를 많이 씁니다"
                checked={cfg.stream_copy}
                onChange={(v) => set("stream_copy", v)}
              />
              {!cfg.stream_copy && (
                <div className="grid gap-4 border-t border-line pt-4">
                  <Field label="영상 코덱">
                    {(id) => (
                      <Select
                        id={id}
                        value={cfg.video_codec}
                        onChange={(e) => set("video_codec", e.target.value)}
                      >
                        <option>libx264</option>
                        <option>libx265</option>
                      </Select>
                    )}
                  </Field>
                  <Field label="프리셋">
                    {(id) => (
                      <Select
                        id={id}
                        value={cfg.preset}
                        onChange={(e) => set("preset", e.target.value)}
                      >
                        {[
                          "ultrafast",
                          "superfast",
                          "veryfast",
                          "faster",
                          "fast",
                          "medium",
                          "slow",
                          "slower",
                          "veryslow",
                        ].map((p) => (
                          <option key={p}>{p}</option>
                        ))}
                      </Select>
                    )}
                  </Field>
                  <Field label="출력 해상도">
                    {(id) => (
                      <Select
                        id={id}
                        value={cfg.postprocess_resolution}
                        onChange={(e) =>
                          set(
                            "postprocess_resolution",
                            e.target.value as Config["postprocess_resolution"],
                          )
                        }
                      >
                        <option value="source">원본</option>
                        <option value="1080p">1080p</option>
                        <option value="720p">720p</option>
                        <option value="480p">480p</option>
                      </Select>
                    )}
                  </Field>
                  <div className="flex items-end">
                    <ToggleRow
                      label="비트레이트 모드"

                      checked={cfg.use_bitrate_mode}
                      onChange={(v) => set("use_bitrate_mode", v)}
                    />
                  </div>
                  {cfg.use_bitrate_mode ? (
                    <>
                      {text("video_bitrate", "영상 비트레이트", "예: 8000k")}
                      {text("vbv_maxrate", "최대 비트레이트 (선택)")}
                      {text("vbv_bufsize", "버퍼 크기 (선택)")}
                    </>
                  ) : (
                    <Field label="CRF (낮을수록 고화질)">
                      {(id) => (
                        <TextInput
                          id={id}
                          type="number"
                          min={0}
                          max={51}
                          value={cfg.video_quality}
                          onChange={(e) =>
                            set("video_quality", Number(e.target.value))
                          }
                        />
                      )}
                    </Field>
                  )}
                  {text("audio_codec", "오디오 코덱")}
                  {text(
                    "audio_bitrate",
                    "오디오 비트레이트",
                    "copy를 쓰면 그대로 복사",
                  )}
                  <div className="sm:col-span-2">
                    {text(
                      "extra_ffmpeg_options",
                      "ffmpeg 추가 옵션",
                      "-vf를 넣으면 위의 해상도 설정은 무시됩니다",
                      true,
                    )}
                  </div>
                </div>
              )}
            </Group>
          </Section>
        </Tabs.Panel>

        <Tabs.Panel value={2} keepMounted>
          <Section>
            <Group title="접근">
              <ToggleRow
                label="파일 관리자 사용"
                checked={cfg.fileManagerEnabled}
                onChange={(v) => set("fileManagerEnabled", v)}
              />
              <Field label="접근 범위">
                {(id) => (
                  <Select
                    id={id}
                    value={cfg.fileManagerMode}
                    onChange={(e) =>
                      set(
                        "fileManagerMode",
                        e.target.value as Config["fileManagerMode"],
                      )
                    }
                  >
                    <option value="blacklist">
                      제한 없음 (시스템 폴더만 차단)
                    </option>
                    <option value="whitelist">허용한 폴더만</option>
                  </Select>
                )}
              </Field>
              {cfg.fileManagerEnabled &&
                cfg.fileManagerMode === "blacklist" && (
                  <Notice tone="warn">
                    제한 없는 모드에서는 로그인한 누구나 시스템 폴더를 제외한
                    모든 파일을 지울 수 있습니다.
                  </Notice>
                )}
              {cfg.fileManagerMode === "whitelist" && (
                <Field
                  label="추가로 허용할 폴더"
                  hint="한 줄에 하나. 채널 저장 폴더와 이동 폴더는 자동으로 허용됩니다"
                >
                  {(id) => (
                    <TextArea
                      id={id}
                      rows={3}
                      value={cfg.fileManagerRoots.join("\n")}
                      onChange={(e) =>
                        set(
                          "fileManagerRoots",
                          e.target.value
                            .split("\n")
                            .map((l) => l.trim())
                            .filter(Boolean),
                        )
                      }
                    />
                  )}
                </Field>
              )}
            </Group>
            <Group title="동작">
              <ToggleRow
                label="읽기 전용"

                checked={cfg.fileManagerReadOnly}
                onChange={(v) => set("fileManagerReadOnly", v)}
              />
              <ToggleRow
                label="휴지통 사용"

                checked={cfg.trashEnabled}
                onChange={(v) => set("trashEnabled", v)}
              />
            </Group>
          </Section>
        </Tabs.Panel>

        <Tabs.Panel value={3} keepMounted>
          <Section>
            <XConnectCard stored={secrets.xCookie} />
            <Group title="치지직">
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="NID_AUT">
                  {(id) => (
                    <TextInput
                      id={id}
                      onFocus={selectMasked}
                      value={sec.chzzk.NID_AUT ?? ""}
                      onChange={(e) =>
                        setSec({
                          ...sec,
                          chzzk: { ...sec.chzzk, NID_AUT: e.target.value },
                        })
                      }
                      autoComplete="off"
                      className="font-mono text-[13px]"
                    />
                  )}
                </Field>
                <Field label="NID_SES">
                  {(id) => (
                    <TextInput
                      id={id}
                      onFocus={selectMasked}
                      value={sec.chzzk.NID_SES ?? ""}
                      onChange={(e) =>
                        setSec({
                          ...sec,
                          chzzk: { ...sec.chzzk, NID_SES: e.target.value },
                        })
                      }
                      autoComplete="off"
                      className="font-mono text-[13px]"
                    />
                  )}
                </Field>
              </div>
            </Group>

            <Group title="YouTube">
              <Field label="쿠키 (Netscape 형식)">
                {(id) => (
                  <TextArea
                    id={id}
                    rows={4}
                    onFocus={selectMasked}
                    value={sec.youtubeCookie}
                    onChange={(e) =>
                      setSec({ ...sec, youtubeCookie: e.target.value })
                    }
                    spellCheck={false}
                  />
                )}
              </Field>
              {text(
                "ytPoToken",
                "PO 토큰",
                "여러 개는 쉼표로 구분합니다.",
                true,
              )}
            </Group>

            <Group title="Telegram 알림">
              <ToggleRow
                label="알림 사용"

                checked={cfg.telegram_enabled}
                onChange={(v) => set("telegram_enabled", v)}
              />
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="봇 토큰">
                  {(id) => (
                    <TextInput
                      id={id}
                      onFocus={selectMasked}
                      value={sec.telegram.token}
                      onChange={(e) =>
                        setSec({
                          ...sec,
                          telegram: { ...sec.telegram, token: e.target.value },
                        })
                      }
                      autoComplete="off"
                      className="font-mono text-[13px]"
                    />
                  )}
                </Field>
                <Field label="채팅 ID">
                  {(id) => (
                    <TextInput
                      id={id}
                      value={sec.telegram.chatId}
                      onChange={(e) =>
                        setSec({
                          ...sec,
                          telegram: { ...sec.telegram, chatId: e.target.value },
                        })
                      }
                      className="font-mono text-[13px]"
                    />
                  )}
                </Field>
              </div>
              <div>
                <Button
                  disabled={dirty}
                  title={
                    dirty ? "저장한 뒤에 테스트할 수 있습니다." : undefined
                  }
                  onClick={() =>
                    testTelegram().then(
                      () => toast("테스트 메시지를 보냈습니다."),
                      (e: Error) => toast(e.message, "error"),
                    )
                  }
                >
                  테스트 메시지 보내기
                </Button>
              </div>
            </Group>
          </Section>
        </Tabs.Panel>
      </div>

      {dirty && (
        <FloatingBar label="설정 저장">
          <span role="status" className="px-1 text-muted">
            {pending ? "저장하는 중…" : "저장하지 않은 변경 사항"}
          </span>
          <Button
            disabled={pending}
            onClick={() => (setCfg(config), setSec(secrets))}
          >
            되돌리기
          </Button>
          <Button variant="primary" onClick={save} disabled={pending}>
            저장
          </Button>
        </FloatingBar>
      )}
    </Tabs.Root>
  );
}
