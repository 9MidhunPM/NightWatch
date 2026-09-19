import {NextRequest,NextResponse} from 'next/server';
import {COOKIE,equal,issueSession,originAllowed} from '@/lib/session';
export const runtime='nodejs';
const attempts=new Map<string,{count:number;until:number}>();
export async function POST(req:NextRequest){
 if(!originAllowed(req.headers.get('origin')))return NextResponse.json({message:'Request origin rejected'},{status:403});
 const key=req.headers.get('x-real-ip')||'shared';const now=Date.now();for(const [k,v]of attempts)if(v.until<now)attempts.delete(k);
 const entry=attempts.get(key)||{count:0,until:now+60000};if(entry.count>=8||attempts.size>10000)return NextResponse.json({message:'Too many attempts. Try again in a minute.'},{status:429});entry.count++;attempts.set(key,entry);
 const length=Number(req.headers.get('content-length')||0);if(!Number.isFinite(length)||length<1||length>4096)return NextResponse.json({message:'Request too large'},{status:413});
 const passphrase=process.env.NW_DASHBOARD_PASSPHRASE,secret=process.env.NW_SESSION_SECRET;
 if(!passphrase||!secret||secret.length<32)return NextResponse.json({message:'Operator access is not configured.'},{status:503});
 let supplied='';try{const data=new URLSearchParams(await req.text());supplied=data.get('passphrase')||'';}catch{return NextResponse.json({message:'Invalid request'},{status:400});}
 if(!equal(supplied,passphrase))return NextResponse.json({message:'That passphrase is incorrect.'},{status:401});
 attempts.delete(key);const response=NextResponse.json({ok:true},{headers:{'Cache-Control':'no-store'}});response.cookies.set(COOKIE,issueSession(secret),{httpOnly:true,secure:process.env.NODE_ENV==='production',sameSite:'strict',path:'/',maxAge:28800});return response;
}
export async function DELETE(req:NextRequest){if(!originAllowed(req.headers.get('origin')))return new Response(null,{status:403});const response=NextResponse.json({ok:true});response.cookies.delete(COOKIE);return response;}
