import type {Connection,Project} from '@/lib/types';

export type WorldPoint=[number,number,number];
export type SceneNode={id:string;kind:'project'|'domain'|'network';label:string;point:WorldPoint};
export type SceneEdge={id:string;from:WorldPoint;to:WorldPoint;kind:string;provenance:string};

function hash(value:string):number{let result=2166136261;for(const char of value){result^=char.charCodeAt(0);result=Math.imul(result,16777619);}return result>>>0;}
function unit(value:string,salt:number):number{return(hash(`${value}:${salt}`)%100000)/100000;}
function move(point:WorldPoint,x:number,z:number):WorldPoint{return[point[0]+x,0,point[2]+z];}
function distance(a:WorldPoint,b:WorldPoint){return Math.hypot(a[0]-b[0],a[2]-b[2]);}

export function worldGraph(projects:Project[],connections:Connection[],includeNetworks:boolean):{nodes:SceneNode[];edges:SceneEdge[];positions:Map<string,WorldPoint>}{
 const owner=new Map<string,string>();projects.forEach(project=>project.resources.forEach(resource=>owner.set(resource.id,project.id)));
 const nodeIds=new Set(projects.map(project=>project.id));
 const links=connections.filter(connection=>connection.kind==='DEPENDS_ON'||connection.kind==='ROUTES_TO'||(includeNetworks&&connection.kind==='MEMBER_OF')).map(connection=>({id:connection.id,kind:connection.kind,provenance:connection.provenance,from:owner.get(connection.source)||connection.source,to:owner.get(connection.target)||connection.target})).filter(link=>nodeIds.has(link.from)||nodeIds.has(link.to));
 links.forEach(link=>{if(link.kind==='ROUTES_TO'&&link.from.startsWith('domain:'))nodeIds.add(link.from);if(link.kind==='MEMBER_OF'&&link.to.startsWith('network:'))nodeIds.add(link.to);});
 const ids=[...nodeIds].sort(),positions=new Map<string,WorldPoint>();
 ids.forEach((id,index)=>{const column=index%5,row=Math.floor(index/5);positions.set(id,[(column-2)*11+(unit(id,1)-.5)*4,0,(row-Math.floor((ids.length-1)/10))*11+(unit(id,2)-.5)*4]);});
 for(let step=0;step<120;step++){const delta=new Map(ids.map(id=>[id,[0,0] as [number,number]]));for(let i=0;i<ids.length;i++)for(let j=i+1;j<ids.length;j++){const a=ids[i],b=ids[j],pa=positions.get(a)!,pb=positions.get(b)!,dx=pa[0]-pb[0],dz=pa[2]-pb[2],d=Math.max(1,Math.hypot(dx,dz)),force=48/(d*d),da=delta.get(a)!,db=delta.get(b)!;da[0]+=dx/d*force;da[1]+=dz/d*force;db[0]-=dx/d*force;db[1]-=dz/d*force;}links.forEach(link=>{const a=positions.get(link.from),b=positions.get(link.to);if(!a||!b)return;const dx=b[0]-a[0],dz=b[2]-a[2],d=Math.max(1,Math.hypot(dx,dz)),force=(d-(link.kind==='DEPENDS_ON'?10:8))*.026,da=delta.get(link.from)!,db=delta.get(link.to)!;da[0]+=dx/d*force;da[1]+=dz/d*force;db[0]-=dx/d*force;db[1]-=dz/d*force;});ids.forEach(id=>{const point=positions.get(id)!,shift=delta.get(id)!;positions.set(id,move(point,Math.max(-.65,Math.min(.65,shift[0]))*.72,Math.max(-.65,Math.min(.65,shift[1]))*.72));});}
 const nodes:SceneNode[]=ids.map(id=>({id,kind:id.startsWith('domain:')?'domain':id.startsWith('network:')?'network':'project',label:id.replace(/^(domain:|network:)/,''),point:positions.get(id)!}));
 const edges=links.flatMap(link=>{const from=positions.get(link.from),to=positions.get(link.to);if(!from||!to||distance(from,to)<.5)return[];const dx=to[0]-from[0],dz=to[2]-from[2],d=Math.hypot(dx,dz),pad=link.kind==='ROUTES_TO'?1.1:3.8;return[{id:link.id,kind:link.kind,provenance:link.provenance,from:move(from,dx/d*pad,dz/d*pad),to:move(to,-dx/d*pad,-dz/d*pad)}];});
 return{nodes,edges,positions};
}
