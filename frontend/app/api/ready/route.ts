import {checkReadiness} from '@/lib/readiness';
export const runtime='nodejs';export const dynamic='force-dynamic';
export async function GET(){const state=await checkReadiness();return Response.json(state,{status:state.status==='ok'?200:503,headers:{'Cache-Control':'no-store'}});}
