import {cookies} from 'next/headers';
import {COOKIE,validSession} from './session';
export async function authenticated(){return validSession((await cookies()).get(COOKIE)?.value,process.env.NW_SESSION_SECRET);}
export function backendURL(path:string){return new URL('/api/'+path,process.env.NW_BACKEND_URL||'http://127.0.0.1:8000');}
export function backendHeaders(operator=false){const headers:Record<string,string>={'x-nightwatch-frontend':process.env.NW_FRONTEND_TOKEN||'','Content-Type':'application/json'};if(operator)headers.Authorization=`Bearer ${process.env.NW_OPERATOR_TOKEN||''}`;return headers;}
export const noStore={'Cache-Control':'no-store'};
