import type {Metadata} from 'next';
import {redirect} from 'next/navigation';
import {authenticated} from '@/lib/server';
import {Shell} from '@/components/shell';
export const dynamic='force-dynamic';
export const metadata:Metadata={title:'NightWatch — Operator console',description:'Your private infrastructure world and evidence-backed operations console.',robots:{index:false,follow:false},alternates:{canonical:null}};
export default async function Layout({children}:{children:React.ReactNode}){if(!await authenticated())redirect('/login');return <Shell>{children}</Shell>;}
