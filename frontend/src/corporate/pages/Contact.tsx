import { useState } from "react";
import { submitContact } from "../api/client";
import { Scene } from "../components/Scene";

export function Contact() {
  const [form, setForm] = useState({ name: "", email: "", company: "", message: "" });
  const [status, setStatus] = useState<"idle" | "sending" | "ok" | "error">("idle");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus("sending");
    const r = await submitContact(form);
    setStatus(r.ok ? "ok" : "error");
  }

  return (
    <Scene className="corp-content-page">
      <div className="corp-scene-inner corp-narrow">
        <h1 className="corp-page-title">聯絡 / Contact</h1>
        {status === "ok" ? (
          <p className="corp-state corp-state-loading" role="status">已收到您的訊息，我們會盡快回覆。</p>
        ) : (
          <form onSubmit={onSubmit} className="corp-form">
            <label>名稱<input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
            <label>電子郵件<input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
            <label>公司<input value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} /></label>
            <label>訊息<textarea rows={4} value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} /></label>
            <button className="corp-btn" disabled={status === "sending"} type="submit">
              {status === "sending" ? "傳送中…" : "送出"}
            </button>
            {status === "error" ? <p className="corp-state corp-state-error" role="alert">送出失敗，請稍後再試。</p> : null}
          </form>
        )}
      </div>
    </Scene>
  );
}
