import {notFound} from 'next/navigation';
import {titles} from '@/lib/fixtures';
import Workspace from '@/components/workspace';
export function generateStaticParams(){return Object.keys(titles).map(section=>({section}))}
export default async function Page({params}:{params:Promise<{section:string}>}){const {section}=await params;if(!titles[section])notFound();return <Workspace section={section}/>}
