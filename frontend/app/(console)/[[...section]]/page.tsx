import {notFound} from 'next/navigation';
import {WorldPage} from '@/components/world-page';
import {Overview,Infrastructure,Reports,Settings} from '@/components/console-pages';import {IncidentView} from '@/components/incident-view';
import {Agent} from '@/components/agent';
import {Deployments} from '@/components/deployments';
export default async function Page({params}:{params:Promise<{section?:string[]}>}){const {section=[]}=await params;const [page,id]=section;if(section.length>2)notFound();switch(page){case undefined:return <WorldPage/>;case 'overview':return <Overview/>;case 'infrastructure':return <Infrastructure/>;case 'incidents':return <IncidentView id={id}/>;case 'agent':return <Agent/>;case 'deployments':return <Deployments/>;case 'reports':return <Reports/>;case 'settings':return <Settings/>;default:notFound();}}
