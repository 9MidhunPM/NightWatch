import type {Project,Connection} from '@/lib/types';

export type WorldPoint=[number,number,number];

function hash(value:string):number{let result=2166136261;for(const char of value){result^=char.charCodeAt(0);result=Math.imul(result,16777619);}return result>>>0;}
function unit(seed:number):number{return (hash(String(seed))%10000)/10000;}

export function islandPositions(projects:Project[]):Map<string,WorldPoint>{
 const positions=new Map<string,WorldPoint>();
 const radius=Math.max(10,Math.sqrt(projects.length)*6.8);
 projects.forEach((project,index)=>{const base=index/projects.length*Math.PI*2;const seed=hash(project.id);const angle=base+(unit(seed)-.5)*.42;const distance=radius+(unit(seed+1)-.5)*4;positions.set(project.id,[Math.cos(angle)*distance,0,Math.sin(angle)*distance]);});
 return positions;
}

export type SceneEdge={id:string;from:WorldPoint;to:WorldPoint;kind:string;provenance:string};
export function sceneEdges(projects:Project[],connections:Connection[],includeNetworks:boolean):SceneEdge[]{
 const positions=islandPositions(projects), owners=new Map<string,string>();
 projects.forEach(project=>project.resources.forEach(resource=>owners.set(resource.id,project.id)));
 return connections.flatMap(connection=>{
  if(connection.kind==='MEMBER_OF'&&!includeNetworks)return [];
  if(connection.kind!=='MEMBER_OF'&&connection.kind!=='ROUTES_TO'&&connection.kind!=='DEPENDS_ON')return [];
  const fromProject=owners.get(connection.source),toProject=owners.get(connection.target);
  const from=fromProject?positions.get(fromProject):undefined,to=toProject?positions.get(toProject):undefined;
  if(from&&to&&fromProject!==toProject)return[{id:connection.id,from,to,kind:connection.kind,provenance:connection.provenance}];
  if(connection.kind==='ROUTES_TO'&&to)return[{id:connection.id,from:[to[0],1.4,to[2]-6],to,kind:connection.kind,provenance:connection.provenance}];
  return[];
 });
}
