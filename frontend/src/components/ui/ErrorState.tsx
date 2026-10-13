import React from 'react';
import { AlertTriangle } from 'lucide-react';
import { Button } from './Button';

export function ErrorState({ title = "Something went wrong", message, onRetry }: { title?: string; message: string; onRetry?: () => void }) {
  return (
    <div className="p-6 border border-rose-900/60 bg-rose-950/20 rounded-lg text-center flex flex-col items-center space-y-3">
      <div className="p-2.5 bg-rose-900/40 text-rose-300 rounded-full">
        <AlertTriangle size={24} />
      </div>
      <div>
        <h4 className="text-sm font-semibold text-rose-200">{title}</h4>
        <p className="text-xs text-rose-300/80 mt-1">{message}</p>
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry} className="mt-2 text-rose-300 border-rose-800 hover:bg-rose-900/40">
          Try Again
        </Button>
      )}
    </div>
  );
}
