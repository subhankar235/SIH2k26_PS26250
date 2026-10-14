"use client";
import { useEffect, useId, useRef } from "react";
import type { ReactNode } from "react";
export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}
export function Modal({
  isOpen,
  onClose,
  title,
  subtitle,
  children,
  footer,
}: ModalProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  useEffect(() => {
    const node = dialog.current;
    if (!node) return;
    if (isOpen && !node.open) node.showModal();
    if (!isOpen && node.open) node.close();
    if (!isOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
      node.close();
    };
  }, [isOpen]);
  return (
    <dialog
      ref={dialog}
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      className="m-auto w-[calc(100%-2rem)] max-w-lg max-h-[90vh] overflow-y-auto overscroll-contain rounded-lg border border-slate-700 bg-slate-900 text-slate-100 p-0 backdrop:bg-black/75"
    >
      <div className="p-4 border-b border-slate-700 flex justify-between items-start">
        <div>
          <h2 id={titleId} className="font-semibold">
            {title}
          </h2>
          {subtitle && <p className="text-sm text-slate-400">{subtitle}</p>}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close modal"
          className="p-2"
        >
          &times;
        </button>
      </div>
      <div className="p-4 space-y-4">{children}</div>
      {footer && <div className="p-4 border-t border-slate-700">{footer}</div>}
    </dialog>
  );
}
