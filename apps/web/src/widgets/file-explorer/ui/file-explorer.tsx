import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { useConfig } from '@/entities/config';
import { fileApi, type FileItem, useFileAction, useFileDisks, useFileList, useFileRoots } from '@/entities/file';
import { useEnqueueUploads } from '@/entities/upload';
import { DeleteDialog, MoveDialog, NameDialog } from '@/features/manage-files';
import { cn } from '@/shared/lib/cn';
import { formatBytes } from '@/shared/lib/format';
import { Button, EmptyState, Icon, Notice, PageHeader, RowMenu, type RowMenuItem, Select, TextInput, useToast } from '@/shared/ui';

type SortKey = 'name' | 'mtime' | 'size';
type Dialog = { kind: 'mkdir' } | { kind: 'rename'; item: FileItem } | { kind: 'move'; items: FileItem[] } | { kind: 'delete'; items: FileItem[] };

const LOCK_REASON = '녹화·후처리·업로드 중인 파일은 바꿀 수 없어요';
const TH = 'sticky top-0 z-10 bg-muted-bg px-3 py-2 text-left text-[0.8rem] font-semibold tracking-[0.02em] text-muted';

/** 파일명은 남는 폭을 모두 쓰고(Filename-Wins), 나머지는 고정 폭 열로 양보한다. */
export function FileExplorer() {
  const config = useConfig();
  const roots = useFileRoots();
  const disks = useFileDisks();
  const toast = useToast();
  const enqueue = useEnqueueUploads();
  const streamCopy = useFileAction((paths: string[]) => fileApi.streamCopy(paths));

  const [path, setPath] = useState<string | null>(null);
  const [pathInput, setPathInput] = useState('');
  const [showHidden, setShowHidden] = useState(false);
  const [filter, setFilter] = useState('');
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'name', desc: false });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [dialog, setDialog] = useState<Dialog | null>(null);

  const list = useFileList(path, showHidden);
  const enabled = config.data?.fileManagerEnabled;

  useEffect(() => {
    if (!path && roots.data?.default) setPath(roots.data.default);
  }, [path, roots.data]);
  useEffect(() => {
    if (list.data?.path) setPathInput(list.data.path);
    setSelected(new Set());
  }, [list.data?.path]);

  const items = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const rows = (list.data?.items ?? []).filter((i) => !q || i.name.toLowerCase().includes(q));
    const dir = sort.desc ? -1 : 1;
    return rows.sort((a, b) => {
      if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
      const c = sort.key === 'size' ? a.size - b.size : sort.key === 'mtime' ? a.mtime.localeCompare(b.mtime) : a.name.localeCompare(b.name, 'ko', { numeric: true });
      return c * dir;
    });
  }, [list.data, filter, sort]);

  if (config.data && !enabled) {
    return (
      <>
        <PageHeader title="파일 관리" />
        <Notice>
          파일 관리자가 꺼져 있습니다. <Link to="/settings" className="text-link underline underline-offset-2">설정 → 파일 관리자</Link>에서 켜세요.
        </Notice>
      </>
    );
  }

  const chosen = items.filter((i) => selected.has(i.path));
  const chosenFiles = chosen.filter((i) => !i.is_dir);
  const anyLocked = chosen.some((i) => i.locked);
  const readOnly = config.data?.fileManagerReadOnly;

  const toggleSort = (key: SortKey) => setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: key !== 'name' }));
  const sortMark = (key: SortKey) => (sort.key === key ? <Icon name="up" size={13} className={cn('ml-1 inline', sort.desc && 'rotate-180')} /> : null);
  const parent = path ? path.replace(/[\\/][^\\/]+[\\/]?$/, '') || path : null;

  const doUpload = (files: FileItem[]) =>
    enqueue.mutate(
      files.map((f) => f.path),
      {
        onSuccess: ({ results }) => {
          const bad = results.filter((r) => !r.ok);
          if (bad.length) toast(`${results.length - bad.length}개 추가, ${bad.length}개 실패: ${bad[0].error}`, 'error');
          else toast(`${results.length}개를 업로드 큐에 추가했습니다`);
        },
        onError: (e) => toast(e.message, 'error'),
      },
    );
  const doStreamCopy = (files: FileItem[]) =>
    streamCopy.mutate(
      files.map((f) => f.path),
      {
        onSuccess: ({ results }) => {
          const bad = results.filter((r) => !r.ok);
          toast(bad.length ? `실패 ${bad.length}개: ${bad[0].error}` : '스트림 복사를 마쳤습니다', bad.length ? 'error' : 'ok');
        },
        onError: (e) => toast(e.message, 'error'),
      },
    );

  const menuFor = (it: FileItem): RowMenuItem[] => {
    const lock = !!it.locked || !!readOnly;
    const reason = readOnly ? '읽기 전용 모드입니다' : LOCK_REASON;
    return [
      ...(it.is_dir ? [] : ([{ label: '다운로드', icon: 'download', onClick: () => window.open(fileApi.downloadUrl(it.path), '_blank', 'noopener') }] as RowMenuItem[])),
      { label: '이름 변경', icon: 'edit', disabled: lock, reason, onClick: () => setDialog({ kind: 'rename', item: it }) },
      { label: '이동', icon: 'move', disabled: lock, reason, onClick: () => setDialog({ kind: 'move', items: [it] }) },
      ...(it.is_dir
        ? []
        : ([
            { label: 'YouTube 업로드', icon: 'upload', disabled: !!it.locked, reason: LOCK_REASON, onClick: () => doUpload([it]) },
            { label: '스트림 복사', icon: 'copy', disabled: lock, reason, onClick: () => doStreamCopy([it]) },
          ] as RowMenuItem[])),
      { label: '삭제', icon: 'trash', danger: true, disabled: lock, reason, onClick: () => setDialog({ kind: 'delete', items: [it] }) },
    ];
  };

  return (
    <>
      <PageHeader title="파일 관리">
        <Button icon="refresh" onClick={() => void list.refetch()} disabled={list.isFetching}>
          새로고침
        </Button>
        <Button icon="folderPlus" onClick={() => setDialog({ kind: 'mkdir' })} disabled={!path || readOnly}>
          새 폴더
        </Button>
      </PageHeader>

      {disks.data && disks.data.usages.length > 0 && (
        <ul className="mb-3 flex flex-wrap gap-2" aria-label="디스크 사용량">
          {disks.data.usages.map((d) => (
            <li key={d.path}>
              <button type="button" onClick={() => setPath(d.path)} className="inline-flex items-center gap-2 rounded-full border border-line bg-muted-bg px-3 py-1 text-[0.8rem] hover:bg-tint" title={`${d.path} 로 이동`}>
                <span className="max-w-48 truncate font-mono font-semibold">{d.label ?? d.path}</span>
                <span className={cn('tnum', d.percent >= 90 ? 'text-rec' : 'text-muted')}>
                  {d.percent}% · {formatBytes(d.free)} 남음
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <form
        className="mb-3 flex flex-wrap items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setPath(pathInput.trim() || null);
        }}
      >
        {roots.data && roots.data.roots.length > 1 && (
          <Select aria-label="루트 선택" className="w-auto! font-mono text-[0.85rem]" value={roots.data.roots.find((r) => path?.startsWith(r)) ?? ''} onChange={(e) => setPath(e.target.value)}>
            {roots.data.roots.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </Select>
        )}
        <Button icon="up" aria-label="상위 폴더" onClick={() => parent && setPath(parent)} disabled={!parent || parent === path} />
        <TextInput aria-label="경로" value={pathInput} onChange={(e) => setPathInput(e.target.value)} className="min-w-64 flex-1 font-mono text-[0.85rem]" placeholder="경로를 입력하고 Enter" />
        <div className="relative">
          <Icon name="search" size={15} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" />
          <TextInput aria-label="이름 검색" value={filter} onChange={(e) => setFilter(e.target.value)} className="w-44 pl-8" placeholder="이름 검색" />
        </div>
        {/* 좁은 화면에서는 열 머리글을 숨기므로 정렬을 선택 상자로 제공한다 */}
        <Select
          aria-label="정렬"
          className="w-auto! sm:hidden"
          value={`${sort.key}-${sort.desc ? 'desc' : 'asc'}`}
          onChange={(e) => {
            const [key, dir] = e.target.value.split('-');
            setSort({ key: key as SortKey, desc: dir === 'desc' });
          }}
        >
          <option value="name-asc">이름순</option>
          <option value="name-desc">이름 역순</option>
          <option value="mtime-desc">최신순</option>
          <option value="mtime-asc">오래된순</option>
          <option value="size-desc">큰 파일순</option>
          <option value="size-asc">작은 파일순</option>
        </Select>
        <label className="flex items-center gap-1.5 text-muted">
          <input type="checkbox" checked={showHidden} onChange={(e) => setShowHidden(e.target.checked)} />
          숨김 파일
        </label>
      </form>

      {selected.size > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg border border-line bg-tint px-3 py-2" role="region" aria-label="선택한 항목 작업">
          <span className="mr-1 font-semibold">{selected.size}개 선택</span>
          <Button small icon="move" disabled={anyLocked || readOnly} onClick={() => setDialog({ kind: 'move', items: chosen })}>
            이동
          </Button>
          <Button small icon="upload" disabled={!chosenFiles.length || chosenFiles.some((f) => f.locked)} onClick={() => doUpload(chosenFiles)}>
            YouTube 업로드
          </Button>
          <Button small icon="copy" disabled={!chosenFiles.length || anyLocked || readOnly} onClick={() => doStreamCopy(chosenFiles)}>
            스트림 복사
          </Button>
          <Button small variant="danger" icon="trash" disabled={anyLocked || readOnly} onClick={() => setDialog({ kind: 'delete', items: chosen })}>
            삭제
          </Button>
          <Button small variant="ghost" onClick={() => setSelected(new Set())}>
            선택 해제
          </Button>
        </div>
      )}

      {(roots.error || list.error) && <Notice tone="rec">{((list.error ?? roots.error) as Error).message}. 경로가 허용 범위 안에 있는지 확인하세요.</Notice>}
      {list.isLoading && <p className="text-muted">불러오는 중…</p>}

      {list.data && items.length === 0 && <EmptyState title={filter ? '검색 결과가 없습니다' : '이 폴더는 비어 있습니다'} />}
      {list.data && items.length > 0 && (
        <div className="max-h-[calc(100vh-18rem)] min-h-48 overflow-auto rounded-xl border border-line bg-card shadow-card">
          <table className="w-full border-collapse sm:min-w-[40rem]">
            <thead>
              <tr>
                <th className={`${TH} w-9`}>
                  <input
                    type="checkbox"
                    aria-label="모두 선택"
                    checked={selected.size === items.length}
                    onChange={(e) => setSelected(e.target.checked ? new Set(items.map((i) => i.path)) : new Set())}
                  />
                </th>
                <th className={TH} aria-sort={sort.key === 'name' ? (sort.desc ? 'descending' : 'ascending') : 'none'}>
                  <button type="button" onClick={() => toggleSort('name')} className="font-semibold">
                    이름{sortMark('name')}
                  </button>
                </th>
                <th className={`${TH} w-[7ch] max-sm:hidden`}>종류</th>
                <th className={`${TH} w-[10ch] text-right max-sm:hidden`} aria-sort={sort.key === 'size' ? (sort.desc ? 'descending' : 'ascending') : 'none'}>
                  <button type="button" onClick={() => toggleSort('size')} className="font-semibold">
                    크기{sortMark('size')}
                  </button>
                </th>
                <th className={`${TH} w-[18ch] text-right max-sm:hidden`} aria-sort={sort.key === 'mtime' ? (sort.desc ? 'descending' : 'ascending') : 'none'}>
                  <button type="button" onClick={() => toggleSort('mtime')} className="font-semibold">
                    수정한 날짜{sortMark('mtime')}
                  </button>
                </th>
                <th className={`${TH} w-12`}>
                  <span className="sr-only">작업</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => {
                const on = selected.has(it.path);
                return (
                  <tr key={it.path} className={cn('border-t border-line hover:bg-tint', on && 'bg-tint')}>
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        aria-label={`${it.name} 선택`}
                        checked={on}
                        onChange={(e) =>
                          setSelected((s) => {
                            const n = new Set(s);
                            if (e.target.checked) n.add(it.path);
                            else n.delete(it.path);
                            return n;
                          })
                        }
                      />
                    </td>
                    <td className="max-w-0 px-3 py-2">
                      <div className="flex items-center gap-2">
                        <Icon name={it.is_dir ? 'folder' : 'file'} size={17} className="shrink-0 text-muted" />
                        {it.is_dir ? (
                          <button type="button" onClick={() => setPath(it.path)} className="min-w-0 truncate text-left font-semibold hover:text-link hover:underline" title={it.name}>
                            {it.name}
                          </button>
                        ) : (
                          <a href={fileApi.downloadUrl(it.path)} className="min-w-0 truncate hover:text-link hover:underline" title={`${it.name} (다운로드)`}>
                            {it.name}
                          </a>
                        )}
                        {it.locked && (
                          <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-line bg-muted-bg px-2 py-0.5 text-[0.8rem] font-semibold text-rec" title={LOCK_REASON}>
                            <Icon name="lock" size={12} />
                            사용 중
                          </span>
                        )}
                      </div>
                      <div className="tnum mt-0.5 pl-[25px] text-[0.8rem] text-muted sm:hidden">
                        {!it.is_dir && `${formatBytes(it.size)} · `}
                        {it.mtime}
                      </div>
                    </td>
                    <td className="px-3 py-2 text-muted max-sm:hidden">{it.ext}</td>
                    <td className="tnum px-3 py-2 text-right text-[0.85rem] text-muted max-sm:hidden">{it.is_dir ? '' : formatBytes(it.size)}</td>
                    <td className="tnum whitespace-nowrap px-3 py-2 text-right text-[0.85rem] text-muted max-sm:hidden">{it.mtime}</td>
                    <td className="px-3 py-2 text-right">
                      <RowMenu label={`${it.name} 작업 메뉴`} items={menuFor(it)} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {dialog?.kind === 'mkdir' && path && <NameDialog kind="mkdir" parent={path} onClose={() => setDialog(null)} />}
      {dialog?.kind === 'rename' && path && <NameDialog kind="rename" parent={path} target={dialog.item} onClose={() => setDialog(null)} />}
      {dialog?.kind === 'move' && path && <MoveDialog items={dialog.items} currentDir={path} roots={roots.data?.roots ?? []} onClose={() => setDialog(null)} />}
      {dialog?.kind === 'delete' && <DeleteDialog items={dialog.items} trashEnabled={!!config.data?.trashEnabled} onClose={() => setDialog(null)} />}
    </>
  );
}
