import assert from 'node:assert/strict';
import test from 'node:test';
import {worldGraph} from '../lib/world-layout';
import type {Project} from '../lib/types';

const projects=[
 {id:'alpha',name:'Alpha',environments:[],health:'HEALTHY',resources:[{id:'api',name:'API'}]},
 {id:'beta',name:'Beta',environments:[],health:'HEALTHY',resources:[{id:'web',name:'Web'}]},
] as unknown as Project[];

test('world graph is stable and renders concrete domain and network endpoints',()=>{
 const connections=[{id:'api:web',source:'api',target:'web',kind:'DEPENDS_ON',provenance:'compose'},{id:'route:api',source:'domain:api.example.com',target:'api',kind:'ROUTES_TO',provenance:'traefik'},{id:'network:api',source:'api',target:'network:mesh',kind:'MEMBER_OF',provenance:'docker'}] as never[];
 const first=worldGraph(projects,connections,true),second=worldGraph(projects,connections,true);
 assert.deepEqual(first.nodes,second.nodes);
 assert.ok(first.nodes.some(node=>node.id==='domain:api.example.com'));
 assert.ok(first.nodes.some(node=>node.id==='network:mesh'));
 assert.equal(first.edges.length,3);
 first.edges.forEach(edge=>assert.notDeepEqual(edge.from,edge.to));
});
