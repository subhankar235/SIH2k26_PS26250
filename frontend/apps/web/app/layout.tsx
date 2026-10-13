import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {title:'Air Power | Decision Intelligence',description:'Synthetic resource planning, evidence intelligence and independent verification.'};
export default function RootLayout({children}:{children:React.ReactNode}) {return <html lang="en"><body>{children}</body></html>}
