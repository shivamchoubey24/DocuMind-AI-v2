import React, { useEffect, useRef, useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import {
  createSession,
  deleteDocument,
  deleteSession,
  getMessages,
  listDocuments,
  listSessions,
  renameSession,
  setSessionScope,
  streamChat,
  uploadDocuments,
} from "../api.js";
import DocumentSidebar from "../components/DocumentSidebar.jsx";
import ChatMessage from "../components/ChatMessage.jsx";
import DocumentPreviewModal from "../components/DocumentPreviewModal.jsx";

// Voice input: Web Speech API isn't standardized yet, so feature-detect and
// simply hide the mic button on browsers that don't support it (Firefox,
// most non-Chromium browsers) instead of breaking anything.
const SpeechRecognitionAPI =
  typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);

const SUGGESTED_QUESTIONS = [
  "Summarize this document in 3 bullet points",
  "What are the key takeaways?",
  "Are there any dates, numbers, or figures worth noting?",
];

const THEME_KEY = "documind_theme";

function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === "dark") {
    root.classList.add("dark");
  } else {
    root.classList.remove("dark");
  }
}

function messagesToMarkdown(title, messages) {
  const lines = [`# ${title}`, ""];
  for (const m of messages) {
    if (m.role === "user") {
      lines.push(`**You:** ${m.content}`, "");
    } else {
      lines.push(`**DocuMind AI:** ${m.content}`, "");
      const srcs = m.sources || [];
      if (srcs.length > 0) {
        lines.push("_Sources:_");
        for (const s of srcs) {
          lines.push(`- ${s.source}${s.page ? ` (p.${s.page})` : ""}`);
        }
        lines.push("");
      }
    }
  }
  return lines.join("\n");
}

export default function Workspace() {
  const { user, logout } = useAuth();
  const [documents, setDocuments] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [uploading, setUploading] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [theme, setTheme] = useState(() => localStorage.getItem(THEME_KEY) || "light");
  const [editingSessionId, setEditingSessionId] = useState(null);
  const [editingTitle, setEditingTitle] = useState("");
  const [previewSource, setPreviewSource] = useState(null);
  const [listening, setListening] = useState(false);
  const [scopedDocumentIds, setScopedDocumentIds] = useState([]);

  const bottomRef = useRef(null);
  const pollRef = useRef(null);
  const inputRef = useRef(null);
  const abortRef = useRef(null);
  const recognitionRef = useRef(null);
  // When sendQuestion() creates a brand-new session mid-flow, setting
  // activeSessionId fires the getMessages effect below. That fetch can
  // resolve *while the SSE stream is still in flight*, overwriting the
  // optimistic user+assistant messages sendQuestion just added and
  // silently swallowing every token event that arrives afterward. This
  // flag lets sendQuestion skip that one redundant, racy fetch.
  const suppressNextFetchRef = useRef(false);

  useEffect(() => {
    refreshDocuments();
    refreshSessions();
    return () => clearInterval(pollRef.current);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  // Keyboard shortcuts: Ctrl/Cmd+K -> new chat, "/" -> focus the input
  // (unless the user is already typing somewhere).
  useEffect(() => {
    function handleKeyDown(e) {
      const tag = document.activeElement?.tagName;
      const isTyping = tag === "INPUT" || tag === "TEXTAREA";

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        handleNewSession();
      } else if (e.key === "/" && !isTyping) {
        e.preventDefault();
        inputRef.current?.focus();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Voice input: set up one SpeechRecognition instance for the component's
  // lifetime. No-op entirely if the browser doesn't support it.
  useEffect(() => {
    if (!SpeechRecognitionAPI) return;
    const recognition = new SpeechRecognitionAPI();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognition.onresult = (event) => {
      let transcript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      setInput(transcript);
    };
    recognition.onend = () => setListening(false);
    recognition.onerror = () => setListening(false);
    recognitionRef.current = recognition;
    return () => recognition.stop();
  }, []);

  function handleToggleVoice() {
    if (!recognitionRef.current) return;
    if (listening) {
      recognitionRef.current.stop();
      setListening(false);
    } else {
      setInput("");
      setListening(true);
      recognitionRef.current.start();
    }
  }

  async function refreshDocuments() {
    try {
      const docs = await listDocuments();
      setDocuments(docs);
      const stillProcessing = docs.some((d) => d.status === "processing");
      clearInterval(pollRef.current);
      if (stillProcessing) {
        pollRef.current = setInterval(refreshDocuments, 2000);
      }
    } catch (e) {
      // non-fatal
    }
  }

  async function refreshSessions(selectId) {
    const list = await listSessions();
    setSessions(list);
    // Only ever auto-select a session when the caller explicitly asks for
    // one (e.g. right after creating it). Otherwise every page load starts
    // on a blank "New chat" screen instead of resuming the last session.
    if (selectId) {
      setActiveSessionId(selectId);
    }
  }

  useEffect(() => {
    if (activeSessionId) {
      const session = sessions.find((s) => s.id === activeSessionId);
      setScopedDocumentIds(session?.document_ids || []);
      if (suppressNextFetchRef.current) {
        suppressNextFetchRef.current = false;
        return;
      }
      getMessages(activeSessionId).then(setMessages).catch(() => setMessages([]));
    } else {
      setMessages([]);
    }
  }, [activeSessionId, sessions]);

  async function handleUpload(files) {
    setUploading(true);
    setError("");
    try {
      await uploadDocuments(files);
      await refreshDocuments();
    } catch (e) {
      setError(e.response?.data?.detail || "Upload failed.");
    } finally {
      setUploading(false);
    }
  }

  async function handleDeleteDocument(id) {
    await deleteDocument(id);
    refreshDocuments();
  }

  async function handleNewSession() {
    setActiveSessionId(null);
    setMessages([]);
    setInput("");
    setScopedDocumentIds([]);
    inputRef.current?.focus();
  }

  async function handleToggleScope(documentId) {
    const next = scopedDocumentIds.includes(documentId)
      ? scopedDocumentIds.filter((id) => id !== documentId)
      : [...scopedDocumentIds, documentId];
    setScopedDocumentIds(next);
    if (activeSessionId) {
      try {
        await setSessionScope(activeSessionId, next);
      } catch (e) {
        // non-fatal; scope will still apply to the next message we send
        // via session creation, and the user can retry the toggle
      }
    }
  }

  async function handleDeleteSession(id) {
    await deleteSession(id);
    if (activeSessionId === id) setActiveSessionId(null);
    refreshSessions();
  }

  function startRenaming(session) {
    setEditingSessionId(session.id);
    setEditingTitle(session.title);
  }

  async function commitRename() {
    const id = editingSessionId;
    const title = editingTitle.trim();
    setEditingSessionId(null);
    if (!id || !title) return;
    try {
      await renameSession(id, title);
      setSessions((prev) => prev.map((s) => (s.id === id ? { ...s, title } : s)));
    } catch (e) {
      // non-fatal; leave the old title in place
    }
  }

  function handleEditUserMessage(content) {
    setInput(content);
    inputRef.current?.focus();
  }

  function handleRegenerate() {
    const lastUser = [...messages].reverse().find((m) => m.role === "user");
    if (lastUser) sendQuestion(lastUser.content);
  }

  function handleStopGenerating() {
    abortRef.current?.abort();
  }

  function handleExportMarkdown() {
    const title = sessions.find((s) => s.id === activeSessionId)?.title || "DocuMind chat";
    const md = messagesToMarkdown(title, messages);
    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title.replace(/[^\w\- ]/g, "").trim() || "chat"}.md`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function sendQuestion(question) {
    if (!question.trim() || sending) return;
    setError("");

    let sessionId = activeSessionId;
    if (!sessionId) {
      const session = await createSession(question.slice(0, 60), scopedDocumentIds);
      sessionId = session.id;
      suppressNextFetchRef.current = true;
      await refreshSessions(sessionId);
    }

    setInput("");
    setSending(true);
    setMessages((prev) => [...prev, { role: "user", content: question, id: `tmp-u-${Date.now()}` }]);
    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: "", sources: [], id: `tmp-a-${Date.now()}`, streaming: true },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChat(
        sessionId,
        question,
        (evt) => {
          if (evt.type === "sources") {
            setMessages((prev) => updateLastAssistant(prev, (m) => ({ ...m, sources: evt.sources })));
          } else if (evt.type === "token") {
            setMessages((prev) =>
              updateLastAssistant(prev, (m) => ({ ...m, content: m.content + evt.text }))
            );
          } else if (evt.type === "done") {
            setMessages((prev) =>
              updateLastAssistant(prev, (m) => ({ ...m, streaming: false, latencyMs: evt.latency_ms }))
            );
          } else if (evt.type === "error") {
            setError(evt.message);
            setMessages((prev) =>
              updateLastAssistant(prev, (m) => ({
                ...m,
                streaming: false,
                content: m.content || `⚠️ ${evt.message}`,
              }))
            );
          }
        },
        controller.signal
      );
    } catch (e) {
      if (e.name === "AbortError") {
        setMessages((prev) => updateLastAssistant(prev, (m) => ({ ...m, streaming: false })));
      } else {
        const msg = e.message || "Something went wrong while streaming the response.";
        setError(msg);
        setMessages((prev) =>
          updateLastAssistant(prev, (m) => ({
            ...m,
            streaming: false,
            content: m.content || `⚠️ ${msg}`,
          }))
        );
      }
    } finally {
      setSending(false);
      abortRef.current = null;
      refreshSessions();
    }
  }

  function updateLastAssistant(list, updater) {
    const copy = [...list];
    for (let i = copy.length - 1; i >= 0; i--) {
      if (copy[i].role === "assistant") {
        copy[i] = updater(copy[i]);
        break;
      }
    }
    return copy;
  }

  const hasReadyDocs = documents.some((d) => d.status === "ready");
  const initials = (user?.full_name || user?.email || "?").trim()[0]?.toUpperCase();
  const isLastMessageAssistant = messages.length > 0 && messages[messages.length - 1].role === "assistant";
  const canRegenerate = isLastMessageAssistant && !sending && messages[messages.length - 1].content;

  return (
    <div className="h-screen flex bg-slate-100 dark:bg-ink-900 text-slate-900 dark:text-slate-100 transition-colors">
      {/* Sessions rail */}
      <div className="w-60 bg-white dark:bg-ink-800 border-r border-slate-200 dark:border-ink-700 flex flex-col">
        <div className="h-14 flex items-center gap-2 px-4 border-b border-slate-200 dark:border-ink-700">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 flex items-center justify-center text-white text-sm shadow-sm">
            📚
          </div>
          <span className="font-semibold text-slate-800 dark:text-slate-100 text-sm">DocuMind AI</span>
          <button
            onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
            title="Toggle dark mode"
            className="ml-auto w-7 h-7 rounded-lg hover:bg-slate-100 dark:hover:bg-ink-700 text-slate-400 dark:text-slate-300 flex items-center justify-center text-sm transition"
          >
            {theme === "dark" ? "☀️" : "🌙"}
          </button>
        </div>
        <div className="p-3">
          <button
            onClick={handleNewSession}
            title="New chat (Ctrl/Cmd+K)"
            className="w-full bg-gradient-to-br from-brand-600 to-brand-700 hover:brightness-110 text-white text-sm font-medium rounded-xl py-2.5 shadow-sm shadow-brand-600/20 transition"
          >
            + New chat
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 space-y-1">
          {sessions.map((s) => (
            <div
              key={s.id}
              onClick={() => editingSessionId !== s.id && setActiveSessionId(s.id)}
              className={`group flex items-center justify-between px-3 py-2 rounded-xl cursor-pointer text-sm transition ${
                s.id === activeSessionId
                  ? "bg-brand-50 dark:bg-brand-900/30 text-brand-700 dark:text-brand-300 font-medium"
                  : "hover:bg-slate-50 dark:hover:bg-ink-700 text-slate-600 dark:text-slate-300"
              }`}
            >
              {editingSessionId === s.id ? (
                <input
                  autoFocus
                  value={editingTitle}
                  onChange={(e) => setEditingTitle(e.target.value)}
                  onBlur={commitRename}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitRename();
                    if (e.key === "Escape") setEditingSessionId(null);
                  }}
                  onClick={(e) => e.stopPropagation()}
                  className="flex-1 bg-white dark:bg-ink-900 border border-brand-300 rounded-lg px-2 py-0.5 text-sm outline-none"
                />
              ) : (
                <span className="truncate">{s.title}</span>
              )}
              {editingSessionId !== s.id && (
                <span className="flex items-center gap-1 opacity-0 group-hover:opacity-100 shrink-0">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      startRenaming(s);
                    }}
                    title="Rename"
                    className="text-slate-400 hover:text-brand-600 text-xs"
                  >
                    ✎
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteSession(s.id);
                    }}
                    title="Delete"
                    className="text-slate-400 hover:text-red-500 text-xs"
                  >
                    ✕
                  </button>
                </span>
              )}
            </div>
          ))}
        </div>
        <div className="p-3 border-t border-slate-200 dark:border-ink-700 flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-full bg-slate-700 text-white text-xs font-semibold flex items-center justify-center shrink-0">
            {initials}
          </div>
          <div className="min-w-0">
            <p className="truncate text-sm font-medium text-slate-700 dark:text-slate-200">
              {user?.full_name || user?.email}
            </p>
            <button onClick={logout} className="text-xs text-brand-600 dark:text-brand-400 hover:underline">
              Sign out
            </button>
          </div>
        </div>
      </div>

      {/* Documents rail */}
      <div className="w-72 bg-slate-50/70 dark:bg-ink-800/60 border-r border-slate-200 dark:border-ink-700 p-3 flex flex-col">
        <h2 className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wide mb-3 px-1">
          Your documents
        </h2>
        <DocumentSidebar
          documents={documents}
          onUpload={handleUpload}
          onDelete={handleDeleteDocument}
          uploading={uploading}
          scopedDocumentIds={scopedDocumentIds}
          onToggleScope={handleToggleScope}
        />
      </div>

      {/* Chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="h-14 border-b border-slate-200 dark:border-ink-700 bg-white/80 dark:bg-ink-800/80 backdrop-blur flex items-center px-6 shrink-0 gap-3">
          <h1 className="font-semibold text-slate-800 dark:text-slate-100 text-sm truncate">
            {sessions.find((s) => s.id === activeSessionId)?.title || "New chat"}
          </h1>
          <span className="text-xs text-slate-400 dark:text-slate-500 hidden sm:inline">
            grounded in your uploaded documents
          </span>
          {messages.length > 0 && (
            <button
              onClick={handleExportMarkdown}
              title="Export this chat as Markdown"
              className="ml-auto text-xs text-slate-500 dark:text-slate-400 hover:text-brand-600 dark:hover:text-brand-400 inline-flex items-center gap-1 border border-slate-200 dark:border-ink-700 rounded-lg px-2.5 py-1.5 hover:border-brand-200 transition"
            >
              ⬇ Export
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-5 bg-gradient-to-b from-slate-50 to-slate-100 dark:from-ink-900 dark:to-ink-900">
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center text-center text-slate-400 dark:text-slate-500">
              <div className="w-14 h-14 rounded-2xl bg-white dark:bg-ink-800 shadow-sm border border-slate-200 dark:border-ink-700 flex items-center justify-center text-2xl mb-3">
                💬
              </div>
              <p className="text-sm max-w-xs">
                {hasReadyDocs
                  ? "Ask a question about your documents to get started."
                  : "Upload a document on the left, then ask a question here."}
              </p>
              <p className="text-xs mt-3 text-slate-300 dark:text-slate-600">
                Tip: press <kbd className="px-1 py-0.5 rounded bg-slate-200 dark:bg-ink-700">/</kbd> to focus the
                input, <kbd className="px-1 py-0.5 rounded bg-slate-200 dark:bg-ink-700">Ctrl/Cmd+K</kbd> for a new
                chat.
              </p>
            </div>
          )}
          {messages.map((m, i) => (
            <ChatMessage
              key={m.id}
              role={m.role}
              content={m.content}
              sources={m.sources}
              latencyMs={m.latencyMs || m.latency_ms}
              streaming={m.streaming}
              onEdit={m.role === "user" ? () => handleEditUserMessage(m.content) : undefined}
              onRegenerate={
                m.role === "assistant" && i === messages.length - 1 && canRegenerate ? handleRegenerate : undefined
              }
              onPreviewSource={(s) => setPreviewSource(s)}
            />
          ))}
          <div ref={bottomRef} />
        </div>

        {error && (
          <div className="px-6 py-2.5 text-sm text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-950/40 border-t border-red-100 dark:border-red-900/50 flex items-center gap-2">
            <span>⚠️</span>
            <span>{error}</span>
          </div>
        )}

        <div className="border-t border-slate-200 dark:border-ink-700 bg-white dark:bg-ink-800 p-4 shrink-0">
          {hasReadyDocs && messages.length === 0 && (
            <div className="flex gap-2 mb-3 flex-wrap">
              {SUGGESTED_QUESTIONS.map((q) => (
                <button
                  key={q}
                  onClick={() => sendQuestion(q)}
                  className="text-xs bg-slate-100 dark:bg-ink-700 hover:bg-slate-200 dark:hover:bg-ink-700/70 text-slate-600 dark:text-slate-300 px-3 py-1.5 rounded-full transition"
                >
                  {q}
                </button>
              ))}
            </div>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              sendQuestion(input);
            }}
            className="flex gap-2"
          >
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={!hasReadyDocs || sending}
              placeholder={
                hasReadyDocs ? "Ask a question about your documents..." : "Upload and process a document first"
              }
              className="flex-1 rounded-2xl border border-slate-300 dark:border-ink-700 bg-white dark:bg-ink-900 text-slate-900 dark:text-slate-100 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand-400 focus:border-transparent disabled:bg-slate-50 dark:disabled:bg-ink-800 transition"
            />
            {SpeechRecognitionAPI && (
              <button
                type="button"
                onClick={handleToggleVoice}
                disabled={!hasReadyDocs || sending}
                title={listening ? "Stop listening" : "Voice input"}
                className={`w-12 shrink-0 rounded-2xl border text-sm transition flex items-center justify-center disabled:opacity-50 ${
                  listening
                    ? "bg-red-500 border-red-500 text-white animate-pulse"
                    : "border-slate-300 dark:border-ink-700 text-slate-400 dark:text-slate-300 hover:text-brand-600 hover:border-brand-300"
                }`}
              >
                {listening ? "●" : "🎤"}
              </button>
            )}
            {sending ? (
              <button
                type="button"
                onClick={handleStopGenerating}
                className="bg-slate-700 hover:bg-slate-800 text-white font-medium rounded-2xl px-6 text-sm shadow-sm transition"
              >
                ◼ Stop
              </button>
            ) : (
              <button
                type="submit"
                disabled={!hasReadyDocs || !input.trim()}
                className="bg-gradient-to-br from-brand-600 to-brand-700 hover:brightness-110 disabled:opacity-50 disabled:hover:brightness-100 text-white font-medium rounded-2xl px-6 text-sm shadow-sm shadow-brand-600/20 transition"
              >
                Send
              </button>
            )}
          </form>
        </div>
      </div>

      {previewSource && (
        <DocumentPreviewModal
          documentId={previewSource.document_id}
          filename={previewSource.source}
          page={previewSource.page}
          onClose={() => setPreviewSource(null)}
        />
      )}
    </div>
  );
}
