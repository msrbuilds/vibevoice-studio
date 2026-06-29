import { useEffect, useRef } from "react";
import { AlertTriangle } from "lucide-react";
import { focusRing } from "@/lib/theme";

export interface ConfirmDialogProps {
  open: boolean;
  isDark: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  isDark,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const confirmRef = useRef<HTMLButtonElement | null>(null);
  const cardRef = useRef<HTMLDivElement | null>(null);

  // Focus the confirm button on open; restore focus on close.
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    confirmRef.current?.focus();
    return () => prev?.focus?.();
  }, [open]);

  // Keyboard: Esc cancels, Enter confirms, Tab is trapped within the card.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCancel();
      } else if (e.key === "Enter") {
        e.preventDefault();
        onConfirm();
      } else if (e.key === "Tab") {
        const card = cardRef.current;
        if (!card) return;
        const focusables = card.querySelectorAll<HTMLElement>("button");
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onCancel, onConfirm]);

  if (!open) return null;

  const surface = isDark ? "bg-zinc-900" : "bg-white";
  const border = isDark ? "border-zinc-800" : "border-gray-200";
  const titleColor = isDark ? "text-zinc-100" : "text-gray-900";
  const msgColor = isDark ? "text-zinc-300" : "text-gray-700";
  const cancelColor = isDark
    ? "text-zinc-300 hover:text-white"
    : "text-gray-700 hover:text-gray-900";
  const confirmColor = danger
    ? "bg-red-600 hover:bg-red-500 text-white"
    : "bg-teal-700 hover:bg-teal-600 text-white";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onCancel}
    >
      <div
        ref={cardRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby="confirm-message"
        className={`${surface} ${border} border rounded-xl shadow-xl w-full max-w-md p-6`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 mb-2">
          {danger && <AlertTriangle className="w-5 h-5 text-red-500 shrink-0" />}
          <h2 id="confirm-title" className={`text-lg font-semibold ${titleColor}`}>
            {title}
          </h2>
        </div>
        <p id="confirm-message" className={`text-sm ${msgColor}`}>
          {message}
        </p>
        <div className="mt-6 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className={`px-4 py-2 text-sm rounded-lg transition-colors ${cancelColor} ${focusRing}`}
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            type="button"
            onClick={onConfirm}
            className={`px-4 py-2 text-sm rounded-lg font-medium transition-colors ${confirmColor} ${focusRing}`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
