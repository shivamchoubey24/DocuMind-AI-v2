import React, { useRef, useState } from "react";

const STATUS_STYLES = {
  ready: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
  processing: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
  failed: "bg-red-50 text-red-700 ring-1 ring-red-200",
};

const ICONS = { pdf: "📄", txt: "📃", docx: "📝" };

export default function DocumentSidebar({
  documents,
  onUpload,
  onDelete,
  uploading,
  scopedDocumentIds = [],
  onToggleScope,
}) {
  const fileInputRef = useRef(null);
  const [dragOver, setDragOver] = useState(false);

  function handleFiles(fileList) {
    if (!fileList || fileList.length === 0) return;
    onUpload(Array.from(fileList));
  }

  return (
    <div className="flex flex-col h-full">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => fileInputRef.current?.click()}
        className={`cursor-pointer border-2 border-dashed rounded-2xl p-5 text-center text-sm transition-all ${
          dragOver
            ? "border-brand-500 bg-brand-50 scale-[1.02]"
            : "border-slate-300 hover:border-brand-400 hover:bg-white"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".pdf,.txt,.docx"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
        <div className="w-10 h-10 mx-auto mb-2 rounded-full bg-brand-100 flex items-center justify-center text-lg">
          {uploading ? (
            <span className="animate-spin inline-block h-4 w-4 rounded-full border-2 border-brand-500 border-t-transparent" />
          ) : (
            "⬆️"
          )}
        </div>
        <p className="text-slate-700 font-medium">
          {uploading ? "Uploading..." : "Drop files or click to upload"}
        </p>
        <p className="text-xs text-slate-400 mt-1">PDF, TXT, DOCX · up to 20MB each</p>
      </div>

      {documents.length > 0 && onToggleScope && (
        <p className="text-[11px] text-slate-400 mt-3 px-0.5">
          {scopedDocumentIds.length > 0
            ? `Scoped to ${scopedDocumentIds.length} document${scopedDocumentIds.length > 1 ? "s" : ""} — check to include more, uncheck all to search everything.`
            : "Check documents to scope this chat to just those (default: searches all)."}
        </p>
      )}

      <div className="mt-2 flex-1 overflow-y-auto space-y-2 pr-1">
        {documents.length === 0 && (
          <div className="text-center mt-10 text-slate-400">
            <p className="text-2xl mb-2">🗂️</p>
            <p className="text-sm">No documents yet.</p>
            <p className="text-xs mt-0.5">Upload something to get started.</p>
          </div>
        )}
        {documents.map((doc) => (
          <div
            key={doc.id}
            className="bg-white border border-slate-200 rounded-xl p-3 text-sm group hover:shadow-sm hover:border-slate-300 transition"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-start gap-2 min-w-0">
                {onToggleScope && doc.status === "ready" && (
                  <input
                    type="checkbox"
                    checked={scopedDocumentIds.includes(doc.id)}
                    onChange={() => onToggleScope(doc.id)}
                    title="Scope chat to this document"
                    className="mt-1 shrink-0 accent-brand-600"
                  />
                )}
                <span className="text-base">{ICONS[doc.extension] || "📄"}</span>
                <div className="min-w-0">
                  <p className="font-medium text-slate-700 truncate" title={doc.filename}>
                    {doc.filename}
                  </p>
                  <p className="text-xs text-slate-400">
                    {doc.num_chunks} chunks{doc.num_pages ? ` · ${doc.num_pages} pages` : ""}
                  </p>
                </div>
              </div>
              <button
                onClick={() => onDelete(doc.id)}
                className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-500 transition text-xs shrink-0 w-5 h-5 flex items-center justify-center rounded-full hover:bg-red-50"
                title="Delete document"
              >
                ✕
              </button>
            </div>
            <span
              className={`inline-block mt-2 text-[11px] font-medium px-2 py-0.5 rounded-full ${
                STATUS_STYLES[doc.status] || "bg-slate-100 text-slate-600"
              }`}
            >
              {doc.status === "processing" ? "Processing…" : doc.status}
            </span>
            {doc.status === "failed" && doc.error_message && (
              <p className="text-xs text-red-500 mt-1">{doc.error_message}</p>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
