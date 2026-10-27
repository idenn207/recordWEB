import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useConfig } from "@/entities/config";
import {
  fileApi,
  type FileItem,
  useFileAction,
  useFileDisks,
  useFileList,
  useFileRoots,
} from "@/entities/file";
import { useEnqueueUploads } from "@/entities/upload";
import { DeleteDialog, MoveDialog, NameDialog } from "@/features/manage-files";
import { cn } from "@/shared/lib/cn";
import { formatBytes } from "@/shared/lib/format";
import {
  Button,
  EmptyState,
  Icon,
  IconButton,
  ListSkeleton,
  Notice,
  PageHeader,
  PillSelect,
  type PillOption,
  RowMenu,
  type RowMenuItem,
  TextInput,
  useToast,
} from "@/shared/ui";

type SortKey = "name" | "mtime" | "size";
type SortValue = `${SortKey}-${"asc" | "desc"}`;
type Dialog =
  | { kind: "mkdir" }
  | { kind: "rename"; item: FileItem }
  | { kind: "move"; items: FileItem[] }
  | { kind: "delete"; items: FileItem[] };

const LOCK_REASON = "녹화, 후처리, 업로드 중인 파일은 바꿀 수 없습니다.";
const TH =
  "sticky top-14 z-10 bg-muted-bg px-3 text-left text-[13px] font-semibold text-muted";
const SORT_OPTIONS: PillOption<SortValue>[] = [
  { value: "name-asc", label: "이름순" },
  { value: "name-desc", label: "이름 역순" },
  { value: "mtime-desc", label: "최신순" },
  { value: "mtime-asc", label: "오래된순" },
  { value: "size-desc", label: "큰 파일순" },
  { value: "size-asc", label: "작은 파일순" },
];
const VIDEO = ["ts", "mp4", "mkv", "flv", "webm", "mov", "m4v"];
const AUDIO = ["mp3", "m4a", "aac", "wav", "flac", "ogg", "opus"];
const kindIcon = (it: FileItem) => {
  if (it.is_dir) return "folder" as const;
  const e = it.ext.replace(/^\./, "").toLowerCase();
  return VIDEO.includes(e)
    ? ("video" as const)
    : AUDIO.includes(e)
      ? ("audio" as const)
      : ("file" as const);
};

/** 파일명은 남는 폭을 모두 쓰고(Filename-Wins), 나머지는 고정 폭 열로 양보한다. */
export function FileExplorer() {
  const config = useConfig();
  const roots = useFileRoots();
  const disks = useFileDisks();
  const toast = useToast();
  const enqueue = useEnqueueUploads();
  const streamCopy = useFileAction((paths: string[]) =>
    fileApi.streamCopy(paths),
  );

  const [path, setPath] = useState<string | null>(null);
  const [pathInput, setPathInput] = useState("");
  const [showHidden, setShowHidden] = useState(false);
  const [filter, setFilter] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({
    key: "name",
    desc: false,
  });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  // 폴더, 검색, 숨김 파일이 바뀌면 보이지 않게 된 항목이 선택에 남지 않도록 선택을 비운다
  useEffect(() => {
    setSelected(new Set());
  }, [path, filter, showHidden]);
  const [dialog, setDialog] = useState<Dialog | null>(null);
  const [editing, setEditing] = useState(false);
  const crumbRef = useRef<HTMLElement>(null);

  const list = useFileList(path, showHidden);
  const enabled = config.data?.fileManagerEnabled;

  useEffect(() => {
    if (!path && roots.data?.default) setPath(roots.data.default);
  }, [path, roots.data]);
  useEffect(() => {
    if (list.data?.path) setPathInput(list.data.path);
    setSelected(new Set());
  }, [list.data?.path]);

  // 이름 변경, 삭제 등으로 사라진 항목은 선택에서 뺀다
  useEffect(() => {
    const live = new Set((list.data?.items ?? []).map((i) => i.path));
    setSelected((s) => {
      const n = new Set([...s].filter((p) => live.has(p)));
      return n.size === s.size ? s : n;
    });
  }, [list.data?.items]);

  useEffect(() => {
    setEditing(false);
    crumbRef.current?.scrollTo({ left: 1e6 });
  }, [list.data?.path]);

  const items = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const rows = (list.data?.items ?? []).filter(
      (i) => !q || i.name.toLowerCase().includes(q),
    );
    const dir = sort.desc ? -1 : 1;
    return rows.sort((a, b) => {
      if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1;
      const c =
        sort.key === "size"
          ? a.size - b.size
          : sort.key === "mtime"
            ? a.mtime.localeCompare(b.mtime)
            : a.name.localeCompare(b.name, "ko", { numeric: true });
      return c * dir;
    });
  }, [list.data, filter, sort]);

  if (config.data && !enabled) {
    return (
      <>
        <PageHeader title="파일" />
        <Notice>
          파일 관리자가 꺼져 있습니다.{" "}
          <Link
            to="/settings"
            className="text-link underline underline-offset-2"
          >
            설정 → 파일 관리자
          </Link>
          에서 켜세요.
        </Notice>
      </>
    );
  }

  const chosen = items.filter((i) => selected.has(i.path));
  const chosenFiles = chosen.filter((i) => !i.is_dir);
  const anyLocked = chosen.some((i) => i.locked);
  const readOnly = config.data?.fileManagerReadOnly;
  // 비활성인 선택 작업 버튼에는 이유를 붙인다
  const whyBlocked = readOnly ? "읽기 전용 모드입니다." : anyLocked ? LOCK_REASON : undefined;

  const toggleSort = (key: SortKey) =>
    setSort((s) =>
      s.key === key ? { key, desc: !s.desc } : { key, desc: key !== "name" },
    );
  const sortMark = (key: SortKey) =>
    sort.key === key ? (
      <Icon
        name="up"
        size={13}
        className={cn("ml-1 inline", sort.desc && "rotate-180")}
      />
    ) : null;
  const ariaSort = (key: SortKey) =>
    sort.key === key ? (sort.desc ? "descending" : "ascending") : "none";
  const rootList = roots.data?.roots ?? [];
  // Windows 경로(드라이브 문자, UNC)는 대소문자를 가리지 않고, 경계는 구분자로만 판정한다
  const norm = (p: string) => {
    const t = p.length > 1 ? p.replace(/[\\/]+$/, "") : p;
    return /^([a-z]:|\\\\)/i.test(t) ? t.toLowerCase().replace(/\//g, "\\") : t;
  };
  const within = (p: string, r: string) => {
    const a = norm(p);
    const b = norm(r);
    const d = b.includes("\\") ? "\\" : "/";
    return a === b || a.startsWith(b.endsWith(d) ? b : b + d);
  };
  const root =
    rootList
      .filter((r) => path && within(path, r))
      .sort((a, b) => b.length - a.length)[0] ?? null;
  const rootOptions: PillOption<string>[] = rootList.map((r) => {
    const d = disks.data?.usages.find((u) => u.path === r);
    return {
      value: r,
      label: r,
      hint: d ? `${formatBytes(d.free)} 남음` : undefined,
      hintClass:
        d && d.percent >= 90
          ? "text-rec"
          : d && d.percent >= 75
            ? "text-warn"
            : undefined,
    };
  });
  // 루트부터 현재 폴더까지 나눠 각 폴더를 눌러 이동하게 한다
  const sep = path?.includes("\\") && !path.includes("/") ? "\\" : "/";
  // Linux 에서는 역슬래시도 파일명의 일부다
  const splitter = sep === "\\" ? /[\\/]/ : /\//;
  const crumbs: { label: string; path: string }[] = [];
  if (path) {
    let acc = root ?? "";
    if (root) crumbs.push({ label: root, path: root });
    for (const seg of path
      .slice(root?.length ?? 0)
      .split(splitter)
      .filter(Boolean)) {
      acc = acc
        ? acc.replace(/[\\/]$/, "") + sep + seg
        : (path.startsWith("/") ? "/" : "") + seg;
      crumbs.push({ label: seg, path: acc });
    }
  }
  const atRoot = !!path && !!root && norm(path) === norm(root);
  const parent =
    path && !atRoot
      ? path.replace(sep === "\\" ? /[\\/][^\\/]+[\\/]?$/ : /\/[^/]+\/?$/, "") || path
      : null;

  const doUpload = (files: FileItem[]) =>
    enqueue.mutate(
      files.map((f) => f.path),
      {
        onSuccess: ({ results }) => {
          const bad = results.filter((r) => !r.ok);
          if (bad.length)
            toast(
              `${results.length - bad.length}개 추가, ${bad.length}개 실패: ${bad[0].error}`,
              "error",
            );
          else toast(`${results.length}개를 업로드 목록에 추가했습니다.`);
        },
        onError: (e) => toast(e.message, "error"),
      },
    );
  const doStreamCopy = (files: FileItem[]) =>
    streamCopy.mutate(
      files.map((f) => f.path),
      {
        onSuccess: ({ results }) => {
          const bad = results.filter((r) => !r.ok);
          toast(
            bad.length
              ? `실패 ${bad.length}개: ${bad[0].error}`
              : "스트림 복사를 마쳤습니다",
            bad.length ? "error" : "ok",
          );
        },
        onError: (e) => toast(e.message, "error"),
      },
    );

  const menuFor = (it: FileItem): RowMenuItem[] => {
    const lock = !!it.locked || !!readOnly;
    const reason = readOnly ? "읽기 전용 모드입니다" : LOCK_REASON;
    return [
      ...(it.is_dir
        ? []
        : ([
            {
              label: "다운로드",
              icon: "download",
              onClick: () =>
                window.open(fileApi.downloadUrl(it.path), "_blank", "noopener"),
            },
          ] as RowMenuItem[])),
      {
        label: "이름 변경",
        icon: "edit",
        disabled: lock,
        reason,
        onClick: () => setDialog({ kind: "rename", item: it }),
      },
      {
        label: "이동",
        icon: "move",
        disabled: lock,
        reason,
        onClick: () => setDialog({ kind: "move", items: [it] }),
      },
      ...(it.is_dir
        ? []
        : ([
            {
              label: "YouTube 업로드",
              icon: "upload",
              disabled: !!it.locked,
              reason: LOCK_REASON,
              onClick: () => doUpload([it]),
            },
            {
              label: "스트림 복사",
              icon: "copy",
              disabled: lock,
              reason,
              onClick: () => doStreamCopy([it]),
            },
          ] as RowMenuItem[])),
      {
        label: "삭제",
        icon: "trash",
        danger: true,
        disabled: lock,
        reason,
        onClick: () => setDialog({ kind: "delete", items: [it] }),
      },
    ];
  };

  return (
    <>
      <PageHeader title="파일">
        <Button
          icon="refresh"
          onClick={() => void list.refetch()}
          disabled={list.isFetching}
        >
          새로고침
        </Button>
        <Button
          icon="folderPlus"
          onClick={() => setDialog({ kind: "mkdir" })}
          disabled={!path || readOnly}
        >
          새 폴더
        </Button>
      </PageHeader>

      <div className="mb-4 flex flex-col gap-2" data-file-toolbar>
        <div className="flex flex-wrap items-center gap-2">
          {rootOptions.length > 0 && (
            <PillSelect
              label="루트 선택"
              mono
              className="w-full sm:w-60"
              value={root ?? ""}
              options={rootOptions}
              onChange={(r) => setPath(r)}
              data-ctl
            />
          )}
          <IconButton
            data-ctl
            icon="up"
            label="상위 폴더"
            className="size-10 border-ink/15"
            onClick={() => parent && setPath(parent)}
            disabled={!parent || parent === path}
          />
          <div
            data-ctl
            className="flex h-10 min-w-0 flex-1 basis-64 items-center rounded-full border border-ink/15 pl-2 pr-1 focus-within:border-brand"
          >
            {editing ? (
              <form
                className="flex h-full min-w-0 flex-1 items-center"
                onSubmit={(e) => {
                  e.preventDefault();
                  setPath(pathInput.trim() || null);
                  setEditing(false);
                }}
              >
                <input
                  autoFocus
                  aria-label="경로"
                  value={pathInput}
                  onChange={(e) => setPathInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key !== "Escape") return;
                    setEditing(false);
                    requestAnimationFrame(() =>
                      document
                        .querySelector<HTMLElement>('[aria-label="경로 직접 입력"]')
                        ?.focus(),
                    );
                  }}
                  className="h-full w-full min-w-0 bg-transparent px-2 font-mono text-sm text-ink"
                />
              </form>
            ) : (
              <nav
                aria-label="경로"
                ref={crumbRef}
                className="flex h-full min-w-0 flex-1 items-center overflow-x-auto [scrollbar-width:none]"
              >
                {crumbs.map((c, i) => (
                  <span key={c.path} className="flex shrink-0 items-center">
                    {i > 0 && (
                      <Icon
                        name="chevron"
                        size={14}
                        className="-rotate-90 text-muted"
                      />
                    )}
                    <button
                      type="button"
                      onClick={() => setPath(c.path)}
                      aria-current={i === crumbs.length - 1 ? "page" : undefined}
                      className={cn(
                        "h-8 max-w-56 truncate rounded-full px-2.5 text-sm font-semibold hover:bg-muted-bg",
                        i === crumbs.length - 1 ? "text-ink" : "text-muted",
                      )}
                    >
                      {c.label}
                    </button>
                  </span>
                ))}
              </nav>
            )}
            <IconButton
              icon={editing ? "x" : "edit"}
              label={editing ? "경로 입력 닫기" : "경로 직접 입력"}
              className="size-8 shrink-0"
              onClick={() => {
                if (!editing) setPathInput(path ?? "");
                setEditing((v) => !v);
              }}
            />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div data-ctl className="relative h-10 min-w-36 flex-1 sm:max-w-80">
            <Icon
              name="search"
              size={16}
              className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted"
            />
            <TextInput
              aria-label="이름 검색"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="pl-10"
              placeholder="이름 검색"
            />
          </div>
          <PillSelect
            label="정렬"
            className="w-40"
            value={`${sort.key}-${sort.desc ? "desc" : "asc"}` as SortValue}
            options={SORT_OPTIONS}
            onChange={(v) => {
              const [key, dir] = v.split("-");
              setSort({ key: key as SortKey, desc: dir === "desc" });
            }}
            data-ctl
          />
          <button
            type="button"
            data-ctl
            aria-pressed={showHidden}
            onClick={() => setShowHidden((v) => !v)}
            className={cn(
              "inline-flex h-10 items-center rounded-full border px-4 text-sm font-semibold transition-colors",
              showHidden
                ? "border-brand text-brand"
                : "border-ink/15 text-muted hover:bg-muted-bg",
            )}
          >
            숨김 파일
          </button>
        </div>
      </div>

      {(roots.error || list.error) && (
        <Notice tone="rec">
          {((list.error ?? roots.error) as Error).message}
        </Notice>
      )}
      {list.isLoading && <ListSkeleton />}

      {list.data && items.length === 0 && (
        <EmptyState
          title={filter ? "검색 결과가 없습니다" : "이 폴더는 비어 있습니다"}
        />
      )}
      {list.data && items.length > 0 && (
        <div className="min-h-48 overflow-x-clip">
          {selected.size > 0 && (
            <div
              role="region"
              aria-label="선택한 항목 작업"
              className="sticky left-9 top-14 z-20 -mb-12 ml-9 flex h-12 w-[calc(100%-2.25rem)] items-center gap-1 rounded-r-xl bg-tint px-3 sm:gap-2"
            >
              <span className="mr-1 whitespace-nowrap text-sm font-semibold text-ink">
                {selected.size}개 선택
              </span>
              <Button
                small
                icon="move"
                aria-label="이동"
                title={whyBlocked}
                disabled={anyLocked || readOnly}
                onClick={() => setDialog({ kind: "move", items: chosen })}
              >
                <span className="max-sm:sr-only">이동</span>
              </Button>
              <Button
                small
                icon="upload"
                aria-label="YouTube 업로드"
                title={anyLocked ? LOCK_REASON : !chosenFiles.length ? "폴더는 올릴 수 없습니다." : undefined}
                disabled={
                  !chosenFiles.length || chosenFiles.some((f) => f.locked)
                }
                onClick={() => doUpload(chosenFiles)}
              >
                <span className="max-sm:sr-only">YouTube 업로드</span>
              </Button>
              <Button
                small
                icon="copy"
                aria-label="스트림 복사"
                title={whyBlocked ?? (!chosenFiles.length ? "폴더는 복사할 수 없습니다." : undefined)}
                disabled={!chosenFiles.length || anyLocked || readOnly}
                onClick={() => doStreamCopy(chosenFiles)}
              >
                <span className="max-sm:sr-only">스트림 복사</span>
              </Button>
              <Button
                small
                variant="danger"
                icon="trash"
                aria-label="삭제"
                title={whyBlocked}
                disabled={anyLocked || readOnly}
                onClick={() => setDialog({ kind: "delete", items: chosen })}
              >
                <span className="max-sm:sr-only">삭제</span>
              </Button>
              <Button
                small
                variant="ghost"
                icon="x"
                aria-label="선택 해제"
                className="ml-auto shrink-0"
                onClick={() => setSelected(new Set())}
              >
                <span className="max-sm:sr-only">선택 해제</span>
              </Button>
            </div>
          )}
          <table className="w-full border-collapse">
            <thead>
              <tr className="h-12">
                <th className={`${TH} relative w-9 rounded-l-xl`}>
                  <label className="absolute inset-0 flex cursor-pointer items-center justify-center">
                    <input
                      type="checkbox"
                      aria-label="모두 선택"
                      checked={selected.size === items.length}
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? new Set(items.map((i) => i.path))
                            : new Set(),
                        )
                      }
                    />
                  </label>
                </th>
                <th className={TH} aria-sort={ariaSort("name")}>
                  <button
                    type="button"
                    onClick={() => toggleSort("name")}
                    className="-my-2 min-w-6 py-2 font-semibold"
                  >
                    이름{sortMark("name")}
                  </button>
                </th>
                <th
                  className={`${TH} w-28 text-right max-sm:hidden`}
                  aria-sort={ariaSort("size")}
                >
                  <button
                    type="button"
                    onClick={() => toggleSort("size")}
                    className="-my-2 min-w-6 py-2 font-semibold"
                  >
                    크기{sortMark("size")}
                  </button>
                </th>
                <th
                  className={`${TH} w-48 text-right max-sm:hidden`}
                  aria-sort={ariaSort("mtime")}
                >
                  <button
                    type="button"
                    onClick={() => toggleSort("mtime")}
                    className="-my-2 min-w-6 py-2 font-semibold"
                  >
                    수정한 날짜{sortMark("mtime")}
                  </button>
                </th>
                <th className={`${TH} w-14 rounded-r-xl`}>
                  <span className="sr-only">작업</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => {
                const on = selected.has(it.path);
                return (
                  <tr
                    key={it.path}
                    className={cn(
                      "h-14 hover:bg-muted-bg",
                      on && "bg-tint hover:bg-tint",
                    )}
                  >
                    <td className="relative w-9 px-3 py-2">
                      <label className="absolute inset-0 flex cursor-pointer items-center justify-center">
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
                      </label>
                    </td>
                    <td className="max-w-0 px-3 py-2">
                      <div className="flex items-center gap-3">
                        <Icon
                          name={kindIcon(it)}
                          size={20}
                          className={cn(
                            "shrink-0",
                            it.is_dir ? "text-brand" : "text-muted",
                          )}
                        />
                        <div className="min-w-0 flex-1">
                          {it.is_dir ? (
                            <button
                              type="button"
                              onClick={() => setPath(it.path)}
                              className="block max-w-full truncate py-0.5 text-left text-base font-semibold hover:text-link hover:underline"
                              title={it.name}
                            >
                              {it.name}
                            </button>
                          ) : (
                            <a
                              href={fileApi.downloadUrl(it.path)}
                              className="block truncate py-0.5 text-base hover:text-link hover:underline"
                              title={`${it.name} (다운로드)`}
                            >
                              {it.name}
                            </a>
                          )}
                          <div className="tnum whitespace-nowrap text-[13px] text-muted sm:hidden">
                            {!it.is_dir && `${formatBytes(it.size)} · `}
                            {it.mtime.slice(5, 16)}
                          </div>
                        </div>
                        {it.locked && (
                          <span
                            className="inline-flex shrink-0 items-center gap-1 rounded-full border border-line bg-muted-bg px-2.5 py-0.5 text-[13px] font-semibold text-rec"
                            title={LOCK_REASON}
                          >
                            <Icon name="lock" size={13} />
                            녹화 중
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="tnum px-3 py-2 text-right text-sm text-muted max-sm:hidden">
                      {it.is_dir ? "" : formatBytes(it.size)}
                    </td>
                    <td className="tnum whitespace-nowrap px-3 py-2 text-right text-sm text-muted max-sm:hidden">
                      {it.mtime}
                    </td>
                    <td className="px-2 py-2 text-right">
                      <RowMenu
                        label={`${it.name} 작업 메뉴`}
                        items={menuFor(it)}
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {dialog?.kind === "mkdir" && path && (
        <NameDialog
          kind="mkdir"
          parent={path}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "rename" && path && (
        <NameDialog
          kind="rename"
          parent={path}
          target={dialog.item}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "move" && path && (
        <MoveDialog
          items={dialog.items}
          currentDir={path}
          roots={roots.data?.roots ?? []}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "delete" && (
        <DeleteDialog
          items={dialog.items}
          trashEnabled={!!config.data?.trashEnabled}
          onClose={() => setDialog(null)}
        />
      )}
    </>
  );
}
