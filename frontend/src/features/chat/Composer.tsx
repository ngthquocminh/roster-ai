import { useState } from "react";
export function Composer({ onSend, isPending }: { onSend: (text: string) => Promise<unknown>; isPending: boolean }) {
  const [draft, setDraft] = useState("");
  const [failed, setFailed] = useState(false);
  const submit = async () => { const text = draft.trim(); if (!text || isPending) return; setFailed(false); try { await onSend(text); setDraft(""); } catch { setFailed(true); } };
  return <div><label htmlFor="chat-composer">Message</label><textarea id="chat-composer" value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); void submit(); } }} />{failed && <p role="alert">Message could not be sent. Your draft is still here.</p>}<button type="button" disabled={!draft.trim() || isPending} onClick={() => void submit()}>Send</button></div>;
}
