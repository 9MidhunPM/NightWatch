import {NextRequest} from 'next/server';
import {authenticated,backendHeaders,backendURL,noStore} from '@/lib/server';
import {originAllowed} from '@/lib/session';
export const runtime='nodejs';export const dynamic='force-dynamic';
const reads=[/^world$/, /^health$/, /^host(?:\/(?:metrics|capabilities))?$/, /^docker\/(?:status|containers(?:\/[\w.-]+)?|networks)$/, /^topology$/, /^incidents(?:\/[\w-]+)?$/, /^resources$/, /^agent\/(?:status|conversations(?:\/[\w-]+)?)$/, /^observability\/beszel$/, /^telemetry\/(?:host|resource)$/, /^reports\/current(?:\.csv)?$/, /^deployments\/(?:status|repositories(?:\/[\w.-]+\/[\w.-]+\/branches)?|plans|project-plans(?:\/[\w-]+)?)$/];
const writes=[/^agent\/(?:messages|stream|conversations(?:\/[\w-]+\/archive)?)$/, /^deployments\/plans$/, /^deployments\/(?:plans|project-plans)\/[\w-]+\/approval$/, /^incidents\/repair-plans\/[\w-]+\/approval$/, /^incidents\/repair-actions\/[\w-]+\/rollback$/];
async function proxy(req:NextRequest,{params}:{params:Promise<{path:string[]}>}){
 if(!await authenticated())return Response.json({message:'Sign in to continue'},{status:401,headers:noStore});
 const path=(await params).path.join('/');const mutation=req.method==='POST';
 if(!(mutation?writes:reads).some(rule=>rule.test(path)))return Response.json({message:'Unknown endpoint'},{status:404});
 if(mutation&&!originAllowed(req.headers.get('origin')))return new Response(null,{status:403});
 let body:string|undefined;
 if(mutation){const reader=req.body?.getReader();let size=0;const chunks:Uint8Array[]=[];if(reader){while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>32768){await reader.cancel();return new Response(null,{status:413});}chunks.push(value);}}body=Buffer.concat(chunks).toString();}
 const url=backendURL(path);for(const key of ['conversation_id','resource_id','range']){const value=req.nextUrl.searchParams.get(key);if(value)url.searchParams.set(key,value);}
 const abort=new AbortController();const timer=setTimeout(()=>abort.abort(),path==='agent/stream'?180000:45000);req.signal.addEventListener('abort',()=>abort.abort(),{once:true});
 try{const response=await fetch(url,{method:req.method,headers:backendHeaders(mutation),body,cache:'no-store',signal:abort.signal,redirect:'error'});const type=response.headers.get('content-type')||'application/json';
 if(type.includes('text/event-stream')&&response.body){const reader=response.body.getReader();const stream=new ReadableStream({async pull(controller){try{const result=await reader.read();if(result.done){clearTimeout(timer);controller.close();}else controller.enqueue(result.value);}catch{clearTimeout(timer);controller.error(new Error('Stream interrupted'));}},cancel(){clearTimeout(timer);abort.abort();return reader.cancel();}});return new Response(stream,{status:response.status,headers:{...noStore,'Content-Type':type,'X-Accel-Buffering':'no'}});}
 if(response.status!==204&&!path.endsWith('.csv')&&!type.toLowerCase().includes('application/json')){clearTimeout(timer);return Response.json({message:response.status>=500?'The backend is temporarily unavailable. Try again shortly.':'The backend returned an unexpected response.'},{status:response.status>=400?response.status:502,headers:noStore});}
 clearTimeout(timer);return new Response(response.status===204?null:await response.arrayBuffer(),{status:response.status,headers:{...noStore,'Content-Type':type,...(path.endsWith('.csv')?{'Content-Disposition':'attachment; filename="nightwatch-report.csv"'}:{})}});
 }catch{clearTimeout(timer);return Response.json({message:'The backend could not be reached. Try again shortly.'},{status:502,headers:noStore});}
}
export {proxy as GET,proxy as POST};
