type Fetcher=(input:string|URL|Request,init?:RequestInit)=>Promise<Response>;
export type Readiness={status:'ok'|'degraded';frontend:'ok';backend:'ok'|'unavailable'};

export async function checkReadiness(fetcher:Fetcher=fetch):Promise<Readiness>{
 try{
  const base=process.env.NW_BACKEND_URL||'http://127.0.0.1:8000';
  const response=await fetcher(new URL('/api/health',base),{cache:'no-store',signal:AbortSignal.timeout(5000)});
  const type=response.headers.get('content-type')||'';
  if(!response.ok||!type.toLowerCase().includes('application/json'))throw new Error('Backend unavailable');
  const body=await response.json() as {status?:unknown};
  if(body.status!=='ok')throw new Error('Backend unavailable');
  return {status:'ok',frontend:'ok',backend:'ok'};
 }catch{return {status:'degraded',frontend:'ok',backend:'unavailable'};}
}
