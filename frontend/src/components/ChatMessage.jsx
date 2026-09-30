import React, { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";

const ICONS = { pdf: "📄", txt: "📃", docx: "📝" };

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1 py-1">
      <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.3s]" />
      <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce [animation-delay:-0.15s]" />
      <span className="w-1.5 h-1.5 rounded-full bg-slate-400 animate-bounce" />
    </span>
  );
}

// Belt-and-suspenders: collapse near-identical source cards client-side too,
// in case an older cached backend response (or a future retriever change)
// ever sends duplicates again.
function dedupeSources(sources) {
  const seen = new Set();
  const unique = [];
  for (const s of sources) {
    const key = `${s.source}|${s.page}|${(s.snippet || "").slice(0, 80)}`;
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(s);
  }
  return unique;
}

export default function ChatMessage({ role, content, sources = [], latencyMs, streaming, onEdit, onRegenerate, onPreviewSource }) {
  const isUser = role === "user";
  const [showSources, setShowSources] = useState(false);
  const [copied, setCopied] = useState(false);
  const isEmpty = !content;
  const uniqueSources = useMemo(() => dedupeSources(sources), [sources]);

  function handleCopy() {
    navigator.clipboard?.writeText(content).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  return (
    <div className={`flex items-end gap-2.5 animate-fade-up ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="w-8 h-8 shrink-0 rounded-full bg-gradient-to-br from-brand-500 via-brand-600 to-accent-500 flex items-center justify-center text-white text-sm shadow-glow">
          ✨
        </div>
      )}

      <div className={`max-w-[75%] ${isUser ? "order-1" : ""}`}>
        <div
          className={`group relative px-4 py-3 text-sm leading-relaxed shadow-card ${
            isUser
              ? "bg-gradient-to-br from-brand-600 to-brand-700 text-white rounded-2xl rounded-br-md"
              : "bg-white dark:bg-ink-800 border border-slate-200/70 dark:border-ink-700 text-slate-800 dark:text-slate-100 rounded-2xl rounded-bl-md"
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{content}</p>
          ) : isEmpty && streaming ? (
            <TypingDots />
          ) : (
            <div className="prose-chat">
              <ReactMarkdown>{content}</ReactMarkdown>
              {streaming && (
                <span className="inline-block w-1.5 h-4 bg-brand-400 animate-pulse ml-0.5 align-text-bottom rounded-sm" />
              )}
            </div>
          )}

          {/* Hover actions: copy (assistant), regenerate (last assistant), edit (user) */}
          {!isUser && !isEmpty && !streaming && (
            <div className="absolute -top-2.5 -right-2.5 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition">
              {onRegenerate && (
                <button
                  onClick={onRegenerate}
                  title="Regenerate response"
                  className="w-7 h-7 rounded-full bg-white dark:bg-ink-700 border border-slate-200 dark:border-ink-600 shadow-card text-slate-400 dark:text-slate-300 hover:text-brand-600 hover:border-brand-200 text-xs flex items-center justify-center"
                >
                  ↻
                </button>
              )}
              <button
                onClick={handleCopy}
                title="Copy response"
                className="w-7 h-7 rounded-full bg-white dark:bg-ink-700 border border-slate-200 dark:border-ink-600 shadow-card text-slate-400 dark:text-slate-300 hover:text-brand-600 hover:border-brand-200 text-xs flex items-center justify-center"
              >
                {copied ? "✓" : "⧉"}
              </button>
            </div>
          )}
          {isUser && onEdit && (
            <button
              onClick={onEdit}
              title="Edit and resend"
              className="absolute -top-2.5 -left-2.5 w-7 h-7 rounded-full bg-white dark:bg-ink-700 border border-slate-200 dark:border-ink-600 shadow-card text-slate-400 dark:text-slate-300 hover:text-brand-600 hover:border-brand-200 text-xs opacity-0 group-hover:opacity-100 transition flex items-center justify-center"
            >
              ✎
            </button>
          )}
        </div>

        {!isUser && uniqueSources.length > 0 && (
          <div className="mt-1.5 ml-1">
            <button
              onClick={() => setShowSources((s) => !s)}
              className="text-xs text-brand-600 dark:text-brand-400 hover:text-brand-800 dark:hover:text-brand-300 hover:underline font-medium inline-flex items-center gap-1"
            >
              <span className={`inline-block transition-transform ${showSources ? "rotate-90" : ""}`}>▸</span>
              {uniqueSources.length} source{uniqueSources.length > 1 ? "s" : ""}
              {latencyMs ? ` · ${(latencyMs / 1000).toFixed(1)}s` : ""}
            </button>
            {showSources && (
              <div className="mt-2 space-y-1.5 animate-fade-up">
                {uniqueSources.map((s, i) => {
                  const canPreview = Boolean(onPreviewSource && s.document_id);
                  return (
                    <div
                      key={i}
                      onClick={canPreview ? () => onPreviewSource(s) : undefined}
                      className={`bg-slate-50 dark:bg-ink-800 border border-slate-200 dark:border-ink-700 rounded-xl px-3 py-2 text-xs hover:border-brand-200 hover:bg-white dark:hover:bg-ink-700 transition ${
                        canPreview ? "cursor-pointer" : ""
                      }`}
                    >
                      <p className="font-medium text-slate-600 dark:text-slate-300 flex items-center gap-1">
                        <span>{ICONS[s.source?.split(".").pop()] || "📄"}</span>
                        <span className="truncate">{s.source}</span>
                        {s.page ? (
                          <span
                            className={`font-normal ${
                              canPreview
                                ? "text-brand-600 dark:text-brand-400 hover:underline"
                                : "text-slate-400 dark:text-slate-500"
                            }`}
                          >
                            · p.{s.page}
                            {canPreview ? " ↗" : ""}
                          </span>
                        ) : null}
                      </p>
                      <p className="text-slate-500 dark:text-slate-400 mt-1 leading-relaxed">{s.snippet}...</p>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {isUser && (
        <div className="w-8 h-8 shrink-0 rounded-full bg-slate-700 dark:bg-slate-600 flex items-center justify-center text-white text-xs font-semibold shadow-sm order-2">
          You
        </div>
      )}
    </div>
  );
}
