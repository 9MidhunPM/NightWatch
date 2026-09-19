import WebSocket from 'ws';
import {authenticated,backendHeaders,backendURL,noStore} from '@/lib/server';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function GET(req:Request){
 if(!await authenticated())return new Response(null,{status:401});
 try{const ticketResponse=await fetch(backendURL('realtime-ticket'),{method:'POST',headers:backendHeaders(),cache:'no-store',signal:AbortSignal.timeout(5000)});if(!ticketResponse.ok)throw Error();const {ticket}=await ticketResponse.json();const url=backendURL('events');url.protocol=url.protocol==='https:'?'wss:':'ws:';const ws=new WebSocket(url,`nightwatch-ticket.${ticket}`,{origin:process.env.NW_FRONTEND_ORIGIN||'http://localhost:3000',handshakeTimeout:5000});
 let stop=()=>{};const stream=new ReadableStream({start(controller){let closed=false;const enc=new TextEncoder();const close=()=>{if(closed)return;closed=true;clearInterval(keepalive);clearTimeout(expire);ws.close();controller.close();};stop=close;const keepalive=setInterval(()=>{if(!closed)controller.enqueue(enc.encode(': keepalive\n\n'));},15000);const expire=setTimeout(close,60000);ws.on('message',data=>{if(!closed)controller.enqueue(enc.encode(`data: ${data.toString()}\n\n`));});ws.on('error',close);ws.on('close',close);req.signal.addEventListener('abort',close,{once:true});},cancel(){stop();}});return new Response(stream,{headers:{...noStore,'Content-Type':'text/event-stream','X-Accel-Buffering':'no'}});
 }catch{return Response.json({message:'Live updates temporarily unavailable'},{status:503,headers:noStore});}
}
