'use client';
import React from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

export function Modal({ isOpen, onClose, title, subtitle, children, footer }: ModalProps) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-150">
      <div className="bg-slate-900 border border-slate-800 rounded-lg shadow-2xl max-w-lg w-full overflow-hidden flex flex-col max-h-[90vh]">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-100">{title}</h2>
            {subtitle && <p className="text-xs text-slate-400 mt-0.5">{subtitle}</p>}
          </div>
          <button onClick={onClose} className="p-1 rounded text-slate-400 hover:text-slate-100 hover:bg-slate-800" aria-label="Close modal">
            <X size={18} />
          </button>
        </div>
        <div className="p-4 overflow-y-auto flex-1 text-sm text-slate-300 space-y-4">
          {children}
        </div>
        {footer && <div className="p-3 bg-slate-950 border-t border-slate-800 flex justify-end gap-2">{footer}</div>}
      </div>
    </div>
  );
}
