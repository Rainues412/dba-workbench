import { useCallback, useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Camera, LockKeyhole, LogOut, Plus, X } from "lucide-react";
import { ApiError } from "../api/client";
import { profileKey, updateProfile, useProfile, type Profile, type ProfileFields } from "../auth/profile";
import { ErrorState, LoadingState } from "./States";

const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp"];
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_IMAGE_PIXELS = 20_000_000;

function Avatar({ name, src }: { name: string; src?: string | null }) {
  return <span className="avatar" aria-hidden="true">
    {src ? <img src={src} alt="" /> : Array.from(name)[0]?.toUpperCase()}
  </span>;
}

export function AccountProfile({ userId, username, logout }: {
  userId: number;
  username: string;
  logout?: () => Promise<void>;
}) {
  const client = useQueryClient();
  const profile = useProfile(userId);
  const name = profile.data?.display_name || username;
  const [editing, setEditing] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);

  async function signOut() {
    setLogoutError(false);
    setLoggingOut(true);
    try {
      await logout?.();
      client.removeQueries({ queryKey: profileKey(userId), exact: true });
    } catch {
      setLogoutError(true);
      setLoggingOut(false);
    }
  }

  return <div className="sidebar-footer">
    <button ref={trigger} className="user-card" type="button" aria-label={`个人资料：${name}`} title={`编辑个人资料 · ${name}`}
      aria-haspopup="dialog" onClick={() => setEditing(true)}>
      <Avatar name={name} src={profile.data?.avatar} />
      <span className="user-copy"><strong>{name}</strong></span>
    </button>
    {logout && <button className="icon-button account-logout" type="button" aria-label="退出登录" title="退出登录"
      disabled={loggingOut} onClick={() => void signOut()}><LogOut size={16} aria-hidden="true" /></button>}
    {logoutError && <p className="account-logout-error" role="alert">退出失败，请重试。</p>}
    {editing && <ProfileDialog username={username} profile={profile} onClose={() => {
      setEditing(false);
      trigger.current?.focus();
    }} onSave={async (revision, fields) => {
      const next = await updateProfile(revision, fields);
      await client.cancelQueries({ queryKey: profileKey(userId), exact: true });
      client.setQueryData(profileKey(userId), next);
    }} />}
  </div>;
}

function ProfileDialog({ username, profile, onClose, onSave }: {
  username: string;
  profile: ReturnType<typeof useProfile>;
  onClose: () => void;
  onSave: (revision: number, fields: ProfileFields) => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const discardTitleId = useId();
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);

  const requestClose = useCallback(() => {
    if (busy || confirmDiscard) return;
    if (dirty) setConfirmDiscard(true);
    else onClose();
  }, [busy, confirmDiscard, dirty, onClose]);

  useEffect(() => {
    if (confirmDiscard) dialog.current?.scrollTo({ top: 0 });
    else dialog.current?.querySelector<HTMLInputElement>('input[name="display_name"]')?.focus();
  }, [confirmDiscard]);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) {
      if (event.key !== "Escape" || event.defaultPrevented || event.isComposing) return;
      event.preventDefault();
      if (confirmDiscard) setConfirmDiscard(false);
      else requestClose();
    }
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [confirmDiscard, requestClose]);

  return createPortal(<>
    <div className="profile-backdrop" aria-hidden="true" />
    <div className="profile-overlay" aria-hidden="true" onClick={requestClose} />
    <dialog open ref={dialog} className="modal profile-dialog" aria-labelledby={titleId}>
      <div inert={confirmDiscard}>
        <button type="button" className="icon-button profile-close" aria-label="关闭个人资料" disabled={busy} onClick={requestClose}><X size={15} /></button>
        {profile.data ? <ProfileForm initial={profile.data} titleId={titleId} username={username} busy={busy} setBusy={setBusy}
          onDirty={setDirty} onCancel={requestClose} onClose={onClose} onSave={onSave} reload={async () => (await profile.refetch({ throwOnError: true })).data} />
          : <div className="profile-details"><h2 id={titleId}>个人资料</h2>
            {profile.isError ? <ErrorState message="无法读取个人资料" retry={() => void profile.refetch()} />
              : <LoadingState label="正在读取个人资料" />}
          </div>}
      </div>
      {confirmDiscard && <div className="profile-discard-layer">
        <section className="profile-discard" role="alertdialog" aria-labelledby={discardTitleId}>
          <h3 id={discardTitleId}>放弃修改？</h3>
          <p>个人资料尚未保存。</p>
          <footer className="modal-actions">
            <button type="button" autoFocus className="button profile-secondary" onClick={() => setConfirmDiscard(false)}>继续编辑</button>
            <button type="button" className="button profile-primary" onClick={onClose}>放弃修改</button>
          </footer>
        </section>
      </div>}
    </dialog>
  </>, document.body);
}

function ProfileForm({ initial, titleId, username, busy, setBusy, reload, onDirty, onCancel, onClose, onSave }: {
  initial: Profile;
  titleId: string;
  username: string;
  busy: boolean;
  setBusy: (value: boolean) => void;
  reload: () => Promise<Profile | undefined>;
  onDirty: (value: boolean) => void;
  onCancel: () => void;
  onClose: () => void;
  onSave: (revision: number, fields: ProfileFields) => Promise<void>;
}) {
  const [saved, setSaved] = useState(initial);
  const [draft, setDraft] = useState<ProfileFields>(initial);
  const [newSpecialty, setNewSpecialty] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [conflict, setConflict] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const specialty = newSpecialty?.trim() ?? "";
  const canAdd = specialty && draft.specialties.length < 12 && !draft.specialties.some((item) => item.toLowerCase() === specialty.toLowerCase());
  const fields: ProfileFields = {
    display_name: draft.display_name.trim(),
    avatar: draft.avatar,
    work_role: draft.work_role.trim(),
    specialties: canAdd ? [...draft.specialties, specialty] : draft.specialties,
    bio: draft.bio.trim(),
  };
  const dirty = fields.display_name !== saved.display_name || fields.avatar !== saved.avatar ||
    fields.work_role !== saved.work_role || fields.bio !== saved.bio ||
    JSON.stringify(fields.specialties) !== JSON.stringify(saved.specialties);
  const tooLong = Array.from(fields.display_name).length > 40;

  useEffect(() => { onDirty(dirty); }, [dirty, onDirty]);

  function changeDraft(fields: Partial<ProfileFields>) {
    setDraft((current) => ({ ...current, ...fields }));
  }

  function addSpecialty() {
    if (canAdd) changeDraft({ specialties: fields.specialties });
    setNewSpecialty(null);
  }

  async function selectAvatar(file?: File) {
    if (!file) return;
    if (!IMAGE_TYPES.includes(file.type) || file.size > MAX_IMAGE_BYTES) {
      setError("请选择 5 MB 以内的 PNG、JPG 或 WebP 图片。");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const source = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = reader.onabort = () => reject(new Error("图片读取失败"));
        reader.readAsDataURL(file);
      });
      const image = new Image();
      image.src = source;
      await image.decode();
      if (image.naturalWidth * image.naturalHeight > MAX_IMAGE_PIXELS) {
        setError("头像图片不能超过 2000 万像素。");
        return;
      }
      changeDraft({ avatar: source });
    } catch {
      setError("无法读取这张图片，请换一张图片。");
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!dirty || busy || conflict || tooLong) return;
    setBusy(true);
    setError("");
    try {
      await onSave(saved.revision, fields);
      onClose();
    } catch (reason) {
      const changed = reason instanceof ApiError && reason.status === 409;
      setConflict(changed);
      setError(changed ? "个人资料已在其他窗口修改。读取最新资料将替换当前草稿。" :
        reason instanceof Error ? reason.message : "保存失败，请重试。");
    } finally {
      setBusy(false);
    }
  }

  async function reloadLatest() {
    setBusy(true);
    try {
      const next = await reload();
      if (!next) return;
      setSaved(next);
      setDraft(next);
      setNewSpecialty(null);
      setConflict(false);
      setError("");
    } catch {
      setError("无法读取最新资料，当前草稿已保留。");
    } finally {
      setBusy(false);
    }
  }

  return <form className="profile-form" onSubmit={(event) => { event.preventDefault(); void save(); }}>
    <section className="profile-photo" aria-label="个人头像">
      <h2>个人头像</h2>
      <Avatar name={fields.display_name || username} src={draft.avatar} />
      <button type="button" className="button profile-primary" disabled={busy} onClick={() => fileInput.current?.click()}><Camera size={13} />更换头像</button>
      <button type="button" className="profile-remove-avatar" disabled={busy || !draft.avatar}
        onClick={() => { changeDraft({ avatar: null }); setError(""); }}>移除头像</button>
      <small>支持 PNG、JPG、WebP，大小不超过 5 MB。</small>
      <input ref={fileInput} type="file" aria-label="头像图片" accept={IMAGE_TYPES.join(",")} hidden onChange={(event) => {
        const file = event.currentTarget.files?.[0];
        event.currentTarget.value = "";
        void selectAvatar(file);
      }} />
    </section>
    <section className="profile-details">
      <h2 id={titleId}>个人资料</h2>
      <div className="profile-fields">
        <label className="profile-field"><span>用户名</span>
          <input name="display_name" autoFocus value={draft.display_name} maxLength={80} placeholder={username} disabled={busy}
            title="用于侧栏和仪表盘，留空时使用登录名" aria-invalid={tooLong || undefined}
            onChange={(event) => changeDraft({ display_name: event.target.value })} />
        </label>
        <label className="profile-field"><span>工作角色</span>
          <input value={draft.work_role} maxLength={40} placeholder="例如：Oracle DBA" disabled={busy}
            onChange={(event) => changeDraft({ work_role: event.target.value })} />
        </label>
        <div className="profile-field"><span>擅长方向</span>
          <div className="profile-specialties" role="group" aria-label="擅长方向">
            {draft.specialties.map((item) => <button className="profile-tag" key={item} type="button" title={item}
              aria-label={`移除擅长方向：${item}`} disabled={busy}
              onClick={() => changeDraft({ specialties: draft.specialties.filter((value) => value !== item) })}>
              <span>{item}</span><X size={12} />
            </button>)}
            {newSpecialty !== null ? <div className="profile-tag-editor">
              <input autoFocus aria-label="添加擅长方向" value={newSpecialty} maxLength={30} disabled={busy}
                onChange={(event) => setNewSpecialty(event.target.value)} onKeyDown={(event) => {
                  if (event.nativeEvent.isComposing) return;
                  if (event.key === "Enter") { event.preventDefault(); addSpecialty(); }
                  if (event.key === "Escape") { event.preventDefault(); setNewSpecialty(null); }
                }} />
              <button className="profile-tag-add" type="button" disabled={busy || !canAdd} onClick={addSpecialty}>添加</button>
            </div> : <button type="button" className="profile-tag-add" disabled={busy || draft.specialties.length >= 12}
              onClick={() => setNewSpecialty("")}><Plus size={13} />添加</button>}
          </div>
        </div>
        <label className="profile-field"><span>个人简介</span>
          <textarea value={draft.bio} rows={2} maxLength={500} placeholder="简单介绍一下你的工作方向" disabled={busy}
            onChange={(event) => changeDraft({ bio: event.target.value })} />
        </label>
      </div>
      <p className="profile-local-note"><LockKeyhole size={12} aria-hidden="true" />资料仅保存在本机。</p>
      {tooLong && <p className="alert error" role="alert">用户名最多 40 个字符。</p>}
      {error && <p className="alert error" role="alert">{error}</p>}
      <footer className="modal-actions">
        <button type="button" className="button profile-secondary" disabled={busy} onClick={onCancel}>取消</button>
        {conflict ? <button type="button" className="button profile-primary" disabled={busy} onClick={() => void reloadLatest()}>读取最新资料</button>
          : <button type="submit" className="button profile-primary" disabled={busy || !dirty || tooLong}>保存</button>}
      </footer>
    </section>
  </form>;
}
