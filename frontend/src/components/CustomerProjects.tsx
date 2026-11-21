import { useEffect, useId, useLayoutEffect, useRef, useState, type Dispatch, type FormEvent, type ReactNode, type RefObject, type SetStateAction } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, ChevronRight, MessageSquare, Plus, SquarePen, Trash2, Users, X } from "lucide-react";
import { ApiError, entityApi, type Entity } from "../api/client";
import { SearchHighlight } from "./SearchHighlight";
import { ErrorState, LoadingState } from "./States";

type Owner = { name: string; label: string };
type Chat = { name: string; platform: string };
type Project = { name: string; chat: Chat; owners: Owner[] };
type Profile = { chat: Chat; owners: Owner[]; projects: Project[] };
type DraftOwner = Owner & { key: string };
type DraftProject = Omit<Project, "owners"> & { key: string; owners: DraftOwner[] };
type Draft = Omit<Profile, "owners" | "projects"> & { owners: DraftOwner[]; projects: DraftProject[] };

const PREVIEW_PROJECTS = 5;
const customerStatusTones = new Map([
  ["活跃", "active"], ["进行中", "in-progress"], ["已暂停", "paused"], ["已结束", "ended"],
]);
const customerStatuses = [...customerStatusTones.keys()];
const chatPlatformTones = new Map([
  ["钉钉", "dingtalk"], ["企业微信", "wecom"], ["微信", "wechat"],
]);
const projectOrder = new Intl.Collator("zh-CN", { numeric: true, sensitivity: "base" });
const emptyChat = () => ({ name: "", platform: "" });
const newKey = () => crypto.randomUUID();

function sortProjects<T extends { name: string }>(projects: T[]): T[] {
  return [...projects].sort((a, b) => projectOrder.compare(a.name.trim(), b.name.trim()));
}

function readProfile(item: Entity): Profile {
  return item.project_profile as Profile;
}

export function makeCustomerDraft(item?: Entity): Draft {
  const profile = item ? readProfile(item) : { chat: emptyChat(), owners: [], projects: [] };
  return {
    ...profile,
    owners: profile.owners.map((owner) => ({ ...owner, key: newKey() })),
    projects: sortProjects(profile.projects).map((project) => ({
      ...project,
      key: newKey(),
      owners: project.owners.map((owner) => ({ ...owner, key: newKey() })),
    })),
  };
}

export function customerProfilePayload(draft: Draft): Profile {
  return {
    chat: draft.chat,
    owners: draft.owners.map(({ name, label }) => ({ name, label })),
    projects: sortProjects(draft.projects).map(({ name, chat, owners }) => ({
      name, chat, owners: owners.map((owner) => ({ name: owner.name, label: owner.label })),
    })),
  };
}

function hasChat(chat: Chat) {
  return Boolean(chat.name.trim() || chat.platform.trim());
}

function ChatSummary({ chat }: { chat: Chat }) {
  const platform = chat.platform.trim();
  return hasChat(chat) ? <span className="customer-chat">
    {platform && <span className="badge customer-platform" data-platform={chatPlatformTones.get(platform)} title={platform}>{platform}</span>}
    {chat.name && <span className="customer-chat-name" title={chat.name}>{chat.name}</span>}
  </span> : <span className="muted">—</span>;
}

function Owners({ owners }: { owners: Owner[] }) {
  return <ul className="customer-owners">{owners.map((owner, index) => <li key={index}>
    <strong title={owner.name}>{owner.name}</strong>
    {owner.label && <span className="badge customer-owner-role" title={owner.label}>{owner.label}</span>}
  </li>)}</ul>;
}

function projectsInList(item: Entity): Project[] {
  const { projects } = readProfile(item);
  const matched = (item.matched_projects as string[] | undefined) ?? [];
  return matched.length ? projects.filter((project) => matched.includes(project.name)) : projects;
}

export function projectInCustomerList(item: Entity, name: string) {
  return projectsInList(item).some((project) => project.name === name);
}

type ProjectFocus = { name: string; key: string };
export type ProjectSelection = { customerId: number; revision: number; index: number; name: string };

export function CustomerDirectory({ rows, disabled, searchQuery, focus, onEdit, onEditProject, onRemove }: {
  rows: Entity[];
  disabled: boolean;
  searchQuery: string;
  focus: (ProjectFocus & { customerId: number }) | null;
  onEdit: (id: number) => void;
  onEditProject: (selection: ProjectSelection) => void;
  onRemove: (item: Entity) => void;
}) {
  return <div className="customer-directory">
    <div className="customer-directory-columns" aria-hidden="true"><span>客户</span><span>负责人</span><span>客户群聊</span><span>状态</span><span>操作</span></div>
    <ul className="customer-directory-list" aria-label="客户清单">{rows.map((item) => <CustomerEntry key={item.id} item={item}
    disabled={disabled} searchQuery={searchQuery} focus={!disabled && focus?.customerId === item.id ? focus : null}
    onEdit={onEdit} onEditProject={onEditProject} onRemove={onRemove} />)}</ul>
  </div>;
}

function CustomerEntry({ item, disabled, searchQuery, focus, onEdit, onEditProject, onRemove }: {
  item: Entity;
  disabled: boolean;
  searchQuery: string;
  focus: ProjectFocus | null;
  onEdit: (id: number) => void;
  onEditProject: (selection: ProjectSelection) => void;
  onRemove: (item: Entity) => void;
}) {
  const [expandedOverride, setExpandedOverride] = useState<boolean | null>(null);
  const [showAll, setShowAll] = useState(false);
  const targetRow = useRef<HTMLTableRowElement>(null);
  const revealed = useRef<string | null>(null);
  const region = useId();
  const name = String(item.name);
  const [animateDisclosure, setAnimateDisclosure] = useState(false);
  const status = String(item.status ?? "");
  const profile = readProfile(item);
  const matching = !!(item.matched_projects as string[] | undefined)?.length;
  const projects = sortProjects(projectsInList(item));
  const allProjects = matching ? sortProjects(profile.projects) : projects;
  const targetIndex = focus ? projects.findIndex((project) => project.name === focus.name) : -1;
  const focusKey = targetIndex >= 0 ? focus?.key : undefined;
  const needsAll = targetIndex >= PREVIEW_PROJECTS;
  const expanded = expandedOverride ?? matching;
  const hasProjects = projects.length > 0;
  const visible = showAll ? projects : projects.slice(0, PREVIEW_PROJECTS);
  useLayoutEffect(() => {
    if (!focusKey) return;
    setExpandedOverride(true);
    if (needsAll) setShowAll(true);
  }, [focusKey, needsAll]);
  useLayoutEffect(() => {
    const row = targetRow.current;
    if (!focusKey || !row || revealed.current === focusKey) return;
    revealed.current = focusKey;
    setAnimateDisclosure(false);
    row.scrollIntoView?.({ block: "center", inline: "nearest", behavior: "instant" });
  }, [focusKey, expanded, showAll]);
  const identity = <>
    <span className="customer-avatar" aria-hidden="true">{Array.from(name)[0]}</span>
    <span className="customer-identity">
      <strong title={name}><SearchHighlight text={name} query={searchQuery} /></strong>
      {hasProjects && <small>{matching ? "匹配 " : ""}{projects.length} 个项目<ChevronRight size={14} aria-hidden="true" /></small>}
    </span>
  </>;
  return <li className="customer-entry">
    <div className="customer-entry-header">
      {hasProjects ? <button type="button" className="customer-heading customer-disclosure" aria-expanded={expanded} aria-controls={region} title={`${expanded ? "收起" : "展开"}${name}的项目`} disabled={disabled}
        onClick={() => {
          setAnimateDisclosure(true);
          setExpandedOverride(!expanded);
          if (!expanded) setShowAll(false);
        }}>
        {identity}
      </button> : <div className="customer-heading">{identity}</div>}
      <div className="customer-shared">
        <div className="customer-owner-summary" role="group" aria-label="负责人">
          <span className="customer-meta-label" aria-hidden="true"><Users size={14} />负责人</span>
          {profile.owners.length ? <Owners owners={profile.owners} /> : <span className="muted">—</span>}
        </div>
        <div className="customer-chat-summary" role="group" aria-label="客户群聊"><span className="customer-meta-label" aria-hidden="true"><MessageSquare size={14} />客户群聊</span><ChatSummary chat={profile.chat} /></div>
      </div>
      <div className="customer-status-cell" role="group" aria-label="状态">{status ? <span className="badge customer-status" data-tone={customerStatusTones.get(status)}>{status}</span> : <span className="muted">—</span>}</div>
      <div className="customer-entry-actions">
        <button type="button" className="icon-button" aria-label="查看/编辑" title={`编辑 ${name}`} disabled={disabled} onClick={() => onEdit(item.id)}><SquarePen size={16} aria-hidden="true" /></button>
        <button type="button" className="icon-button danger" aria-label="删除" title={`删除 ${name}`} disabled={disabled} onClick={() => onRemove(item)}><Trash2 size={16} /></button>
      </div>
    </div>
    {hasProjects && <div id={region} className="customer-entry-disclosure" data-expanded={expanded} data-animate={animateDisclosure} inert={!expanded} aria-hidden={!expanded || undefined}>
      <div className="customer-entry-disclosure-content">{(expanded || expandedOverride !== null) && <div className="customer-entry-details">
      <h3 className="sr-only" id={`${region}-heading`}>项目清单</h3>
      <div className="table-wrap"><table className="customer-project-table" aria-labelledby={`${region}-heading`}>
        <thead><tr><th scope="col">项目名</th><th scope="col">项目群聊</th><th scope="col">项目负责人</th><th scope="col" className="customer-project-action"><span className="sr-only">操作</span></th></tr></thead>
        <tbody>{visible.map((project, index) => <tr key={index} aria-current={index === targetIndex ? true : undefined} ref={index === targetIndex ? targetRow : undefined}>
          <td data-label="项目名"><strong title={project.name}><SearchHighlight text={project.name} query={searchQuery} /></strong></td>
          <td data-label="项目群聊"><ChatSummary chat={project.chat} /></td>
          <td data-label="项目负责人">{project.owners.length ? <Owners owners={project.owners} /> : <span className="muted">{profile.owners.length ? "沿用客户负责人" : "—"}</span>}</td>
          <td className="customer-project-action"><button type="button" className="icon-button" aria-label={`编辑项目 ${project.name}`} title="编辑项目" disabled={disabled}
            onClick={() => onEditProject({ customerId: item.id, revision: item.revision, index: allProjects.indexOf(project), name: project.name })}><SquarePen size={13} aria-hidden="true" /></button></td>
        </tr>)}</tbody>
      </table></div>
      {projects.length > PREVIEW_PROJECTS && <button type="button" className="button small customer-more" onClick={() => setShowAll(!showAll)}>{showAll ? "收起" : `查看更多（全部 ${projects.length} 个项目）`}</button>}
      </div>}</div>
    </div>}
  </li>;
}

export function CustomerProjectDrawer({ customerId, projectName, returnFocus, onClose }: {
  customerId: number;
  projectName: string;
  returnFocus: RefObject<HTMLInputElement | null>;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useId();
  const customer = useQuery({
    queryKey: ["customers", "detail", customerId],
    queryFn: () => entityApi.detail<Entity>("/api/customers/", customerId),
  });
  useLayoutEffect(() => {
    const element = dialog.current!;
    const root = document.documentElement;
    const overflow = root.style.overflow;
    root.style.overflow = "hidden";
    element.showModal();
    return () => {
      element.close();
      root.style.overflow = overflow;
      returnFocus.current?.focus({ preventScroll: true });
    };
  }, [returnFocus]);
  const profile = customer.data ? readProfile(customer.data) : null;
  const projects = profile?.projects.filter((project) => project.name === projectName) ?? [];
  return <dialog ref={dialog} className="customer-project-drawer" aria-labelledby={heading}
    onCancel={(event) => { event.preventDefault(); onClose(); }}>
    <header className="customer-project-drawer-header">
      <h2 id={heading}>{projectName}</h2>
      <button type="button" className="icon-button" aria-label="关闭项目详情" onClick={onClose}><X size={19} /></button>
    </header>
    {customer.isPending ? <LoadingState /> : customer.isError ? <ErrorState message="客户资料加载失败" retry={() => void customer.refetch()} /> : <>
      <p className="muted">所属客户 · {String(customer.data.name)}</p>
      {!projects.length ? <p role="status" className="muted">这个项目已改名或移除。</p> : projects.map((project, index) => <dl className="customer-project-facts" key={index}>
        <dt>项目群聊</dt><dd><ChatSummary chat={project.chat} /></dd>
        <dt>项目负责人</dt><dd>{project.owners.length ? <Owners owners={project.owners} /> : profile?.owners.length ? <><span className="muted">沿用客户负责人</span><Owners owners={profile.owners} /></> : "—"}</dd>
      </dl>)}
    </>}
  </dialog>;
}

export function CustomerProjectEditor({ selection, onClose, onRefresh, onSaved }: {
  selection: ProjectSelection;
  onClose: () => void;
  onRefresh: () => void;
  onSaved: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useId();
  const detail = useQuery({
    queryKey: ["customers", "edit-project", selection.customerId, selection.revision],
    queryFn: () => entityApi.detail<Entity>("/api/customers/", selection.customerId),
    gcTime: 0,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  useLayoutEffect(() => {
    const element = dialog.current!;
    const root = document.documentElement;
    const overflow = root.style.overflow;
    const previousFocus = document.activeElement;
    root.style.overflow = "hidden";
    element.showModal();
    return () => {
      element.close();
      root.style.overflow = overflow;
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus({ preventScroll: true });
    };
  }, []);
  const item = detail.data;
  const target = item && sortProjects(readProfile(item).projects)[selection.index];
  return <dialog ref={dialog} className="modal customer-modal customer-project-modal" aria-labelledby={heading}
    onCancel={(event) => { event.preventDefault(); onClose(); }}>
    <header className="modal-header">
      <div><h2 id={heading}>编辑项目</h2>{item && <small className="muted" title={String(item.name)}>{String(item.name)}</small>}</div>
      <button type="button" className="icon-button modal-close" onClick={onClose} aria-label="关闭"><X size={19} /></button>
    </header>
    {detail.isPending ? <LoadingState /> : detail.isError ? <ErrorState message="客户资料加载失败" retry={() => void detail.refetch()} />
      : item && item.revision === selection.revision && target?.name === selection.name
        ? <CustomerProjectEditForm item={item} index={selection.index} onClose={onClose} onSaved={onSaved} />
        : <div className="alert error" role="alert"><span>客户项目已更新，请重新选择。</span><button type="button" className="button small" onClick={onRefresh}>刷新清单</button></div>}
  </dialog>;
}

function CustomerProjectEditForm({ item, index, onClose, onSaved }: { item: Entity; index: number; onClose: () => void; onSaved: () => void }) {
  const [draft, setDraft] = useState(() => makeCustomerDraft(item));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const platformOptions = useId();
  const contactOptions = useId();
  const nameInput = useRef<HTMLInputElement>(null);
  useEffect(() => { nameInput.current?.focus({ preventScroll: true }); }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await entityApi.update("/api/customers/", item.id, item.revision, { project_profile: customerProfilePayload(draft) });
      onSaved();
    } catch (reason) {
      setError(reason instanceof ApiError && reason.status === 409
        ? "客户项目已在其他窗口更新。请关闭弹窗，刷新清单后重新编辑。"
        : reason instanceof ApiError ? reason.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  return <form className="customer-edit-form" onSubmit={submit}>
    <div className="customer-edit-content">
      <CustomerFieldOptions item={item} owners={draft.owners} platformOptions={platformOptions} contactOptions={contactOptions} />
      <fieldset className="customer-field-group" aria-label="项目信息">
        <ProjectFields project={draft.projects[index]} platformOptions={platformOptions} contactOptions={contactOptions} nameInput={nameInput}
          onChange={(change) => setDraft((current) => ({ ...current, projects: current.projects.map((project, position) => position === index ? { ...project, ...change } : project) }))} />
      </fieldset>
    </div>
    <footer className="customer-edit-footer">
      {error && <div className="alert error" role="alert">{error}</div>}
      <div className="modal-actions"><button type="button" className="button" onClick={onClose}>取消</button><button className="button primary" disabled={busy}>{busy ? "保存中…" : <><CheckCircle2 size={17} />保存</>}</button></div>
    </footer>
  </form>;
}

export function CustomerFields({ item, draft, setDraft }: {
  item?: Entity;
  draft: Draft;
  setDraft: Dispatch<SetStateAction<Draft>>;
}) {
  const platformOptions = useId();
  const contactOptions = useId();
  const [addedProjectKey, setAddedProjectKey] = useState<string | null>(null);
  const addedProjectName = useRef<HTMLInputElement>(null);
  const status = String(item?.status ?? "活跃");
  useLayoutEffect(() => {
    const input = addedProjectName.current;
    input?.scrollIntoView?.({ block: "center", inline: "nearest", behavior: "instant" });
    input?.focus({ preventScroll: true });
  }, [addedProjectKey]);
  function addProject() {
    const project = { key: newKey(), name: "", chat: emptyChat(), owners: [] };
    setDraft((current) => ({ ...current, projects: [project, ...current.projects] }));
    setAddedProjectKey(project.key);
  }
  function updateProject(key: string, change: Partial<DraftProject>) {
    setDraft((current) => ({ ...current, projects: current.projects.map((project) => project.key === key ? { ...project, ...change } : project) }));
  }
  return <>
    <CustomerFieldOptions item={item} owners={draft.owners} platformOptions={platformOptions} contactOptions={contactOptions} />
    <fieldset className="customer-field-group full">
      <legend>客户信息</legend>
      <div className="form-grid">
        <label>客户名<input name="name" defaultValue={String(item?.name ?? "")} required pattern={".*\\S.*"} /></label>
        <label>状态<select name="status" aria-label="状态" defaultValue={status}>{[...new Set([...customerStatuses, status])].map((value) => <option key={value}>{value}</option>)}</select></label>
        <ChatFields chat={draft.chat} scope="客户" options={platformOptions} onChange={(chat) => setDraft((current) => ({ ...current, chat }))} />
      </div>
      <OwnerFields owners={draft.owners} title="负责人" contactOptions={contactOptions} onChange={(owners) => setDraft((current) => ({ ...current, owners }))} />
    </fieldset>
    <section className="customer-project-editor full" aria-label="项目清单">
      <div className="customer-form-heading"><h3>项目清单</h3><button type="button" className="button small" onClick={addProject}><Plus size={15} />新增项目</button></div>
      {!draft.projects.length && <p className="muted">暂无项目，可先保存客户群聊和负责人。</p>}
      {draft.projects.map((project, index) => <fieldset className="customer-field-group" key={project.key}>
        <legend>项目 {index + 1}</legend>
        <ProjectFields project={project} platformOptions={platformOptions} contactOptions={contactOptions}
          nameInput={project.key === addedProjectKey ? addedProjectName : undefined} onChange={(change) => updateProject(project.key, change)}
          nameAction={<button type="button" className="icon-button danger" aria-label={`移除项目 ${index + 1}`} title="移除项目" onClick={() => setDraft((current) => ({
            ...current, projects: current.projects.filter(({ key }) => key !== project.key),
          }))}><Trash2 size={16} /></button>} />
      </fieldset>)}
    </section>
    <label className="full">备注<textarea name="notes" defaultValue={String(item?.notes ?? "")} rows={3} /></label>
  </>;
}

function CustomerFieldOptions({ item, owners, platformOptions, contactOptions }: { item?: Entity; owners: Owner[]; platformOptions: string; contactOptions: string }) {
  const contacts = (item?.contacts ?? []) as { name: string }[];
  const names = new Set([...contacts, ...owners].map(({ name }) => name).filter((name) => name.trim()));
  return <>
    <datalist id={platformOptions}>{[...chatPlatformTones.keys()].map((platform) => <option key={platform} value={platform} />)}</datalist>
    <datalist id={contactOptions}>{[...names].map((name) => <option key={name} value={name} />)}</datalist>
  </>;
}

function ProjectFields({ project, platformOptions, contactOptions, nameInput, nameAction, onChange }: {
  project: DraftProject;
  platformOptions: string;
  contactOptions: string;
  nameInput?: RefObject<HTMLInputElement | null>;
  nameAction?: React.ReactNode;
  onChange: (change: Partial<DraftProject>) => void;
}) {
  return <>
    <div className="customer-form-heading">
      <label>项目名<input ref={nameInput} value={project.name} onChange={(event) => onChange({ name: event.target.value })} required pattern={".*\\S.*"} /></label>
      {nameAction}
    </div>
    <div className="form-grid"><ChatFields chat={project.chat} scope="项目" options={platformOptions} onChange={(chat) => onChange({ chat })} /></div>
    <OwnerFields owners={project.owners} title="项目负责人" contactOptions={contactOptions} onChange={(owners) => onChange({ owners })} />
  </>;
}

function ChatFields({ chat, scope, options, onChange }: { chat: Chat; scope: string; options: string; onChange: (chat: Chat) => void }) {
  return <>
    <label>{scope}群聊名<input value={chat.name} onChange={(event) => onChange({ ...chat, name: event.target.value })} /></label>
    <label>{scope}群聊平台<input list={options} value={chat.platform} placeholder="钉钉 / 企业微信 / 微信" onChange={(event) => onChange({ ...chat, platform: event.target.value })} /></label>
  </>;
}

function OwnerFields({ owners, title, contactOptions, onChange }: { owners: DraftOwner[]; title: string; contactOptions: string; onChange: (owners: DraftOwner[]) => void }) {
  function update(key: string, change: Partial<Owner>) {
    onChange(owners.map((owner) => owner.key === key ? { ...owner, ...change } : owner));
  }
  return <div className="customer-owner-editor" role="group" aria-label={title}>
    <div className="customer-form-heading"><strong>{title}</strong><button type="button" className="button small" onClick={() => onChange([...owners, { key: newKey(), name: "", label: "" }])}><Plus size={14} />添加{title}</button></div>
    {owners.map((owner, index) => <div className="customer-owner-row" key={owner.key}>
      <label>负责人姓名<input list={contactOptions} value={owner.name} onChange={(event) => update(owner.key, { name: event.target.value })} required pattern={".*\\S.*"} /></label>
      <label>职责标签<input value={owner.label} placeholder="如资源开通、技术支持" onChange={(event) => update(owner.key, { label: event.target.value })} /></label>
      <button type="button" className="icon-button danger" title="移除负责人" aria-label={`移除负责人 ${index + 1}`} onClick={() => onChange(owners.filter(({ key }) => key !== owner.key))}><Trash2 size={16} /></button>
    </div>)}
  </div>;
}
