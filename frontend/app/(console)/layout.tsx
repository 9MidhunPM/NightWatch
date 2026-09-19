import {redirect} from 'next/navigation';
import {authenticated} from '@/lib/server';
import {Shell} from '@/components/shell';
export const dynamic='force-dynamic';
export default async function Layout({children}:{children:React.ReactNode}){if(!await authenticated())redirect('/login');return <Shell>{children}</Shell>;}
