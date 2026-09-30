import React, { useEffect, useState } from "react";
import { getDocumentFileUrl, checkDocumentFileExists } from "../api.js";

/**
 * Inline preview for a cited source. PDFs render in the browser's native
 * PDF viewer via an <iframe> with a #page=N fragment (supported by
 * Chrome/Edge/Firefox). Other file types (.docx, .txt) can't be rendered
 * inline by the browser, so we show a lightweight fallback with an "open
 * in new tab" link instead of a blank/broken iframe.
 *
 * Before rendering the iframe we HEAD-check that the file still exists.
 * Pointing the iframe straight at the endpoint used to mean that, for a
 * document that had since been deleted (or a citation left over from before
 * a re-upload), the browser's own PDF viewer would silently render its
 * "file not found" page *inside* our modal — indistinguishable from the
 * preview being broken. We now surface our own clear message instead.
 */
export default function DocumentPreviewModal({ documentId, filename, page, onClose }) {
  const [fileStatus, setFileStatus] = useState("checking"); // checking | ok | missing

  useEffect(() => {
    function handleKey(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  useEffect(() => {
    if (!documentId) return;
    let cancelled = false;
    setFileStatus("checking");
    checkDocumentFileExists(documentId).then((exists) => {
      if (!cancelled) setFileStatus(exists ? "ok" : "missing");
    });
    return () => {
      cancelled = true;
    };
  }, [documentId]);

  if (!documentId) return null;

  const ext = filename?.split(".").pop()?.toLowerCase();
  const fileUrl = getDocumentFileUrl(documentId);
  const isPdf = ext === "pdf";

  return (
    <div
      className="fixed inset-0 z-50 bg-slate-900/60 dark:bg-black/70 flex items-center justify-center p-4 sm:p-8 animate-fade-up"
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-ink-800 rounded-2xl shadow-2xl w-full max-w-4xl h-full max-h-[90vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="h-12 px-4 flex items-center justify-between border-b border-slate-200 dark:border-ink-700 shrink-0">
          <p className="text-sm font-medium text-slate-700 dark:text-slate-200 truncate">
            {filename} {page ? <span className="text-slate-400 dark:text-slate-500 font-normal">· page {page}</span> : null}
          </p>
          <div className="flex items-center gap-3 shrink-0">
            <a
              href={fileUrl}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-brand-600 dark:text-brand-400 hover:underline"
            >
              Open in new tab ↗
            </a>
            <button
              onClick={onClose}
              className="w-7 h-7 rounded-lg hover:bg-slate-100 dark:hover:bg-ink-700 text-slate-400 dark:text-slate-300 flex items-center justify-center"
              title="Close"
            >
              ✕
            </button>
          </div>
        </div>

        <div className="flex-1 bg-slate-100 dark:bg-ink-900 overflow-hidden">
          {fileStatus === "checking" ? (
            <div className="h-full flex items-center justify-center text-sm text-slate-400 dark:text-slate-500">
              Loading preview…
            </div>
          ) : fileStatus === "missing" ? (
            <div className="h-full flex flex-col items-center justify-center text-center text-slate-400 dark:text-slate-500 px-6">
              <div className="w-12 h-12 rounded-xl bg-white dark:bg-ink-800 shadow-sm border border-slate-200 dark:border-ink-700 flex items-center justify-center text-xl mb-3">
                🗂️
              </div>
              <p className="text-sm max-w-xs">
                This document's original file is no longer available (it may have been deleted or
                re-uploaded since this citation was generated).
              </p>
            </div>
          ) : isPdf ? (
            <iframe
              title={filename}
              src={`${fileUrl}#page=${page || 1}`}
              className="w-full h-full border-0"
            />
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-center text-slate-400 dark:text-slate-500 px-6">
              <div className="w-12 h-12 rounded-xl bg-white dark:bg-ink-800 shadow-sm border border-slate-200 dark:border-ink-700 flex items-center justify-center text-xl mb-3">
                📄
              </div>
              <p className="text-sm max-w-xs">
                Inline preview isn't available for .{ext} files yet — open it in a new tab to view it.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
