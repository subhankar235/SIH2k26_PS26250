export function cn(...inputs: (string | boolean | undefined | null | { [key: string]: boolean })[]): string {
  return inputs
    .flatMap((input) => {
      if (!input) return [];
      if (typeof input === 'string') return input.split(' ');
      if (typeof input === 'object') {
        return Object.entries(input)
          .filter(([_, v]) => Boolean(v))
          .map(([k]) => k);
      }
      return [];
    })
    .filter(Boolean)
    .join(' ');
}

export function formatTime(isoOrStr: string) {
  if (!isoOrStr) return '';
  if (isoOrStr.includes(':') && !isoOrStr.includes('T')) return isoOrStr;
  try {
    return new Date(isoOrStr).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return isoOrStr;
  }
}
