import assert from 'node:assert/strict';
import test from 'node:test';
import {islandPositions,sceneEdges} from '../lib/world-layout';
import type {Project} from '../lib/types';

const projects=[
 {id:'alpha',name:'Alpha',environments:[],health:'HEALTHY',resources:[{id:'api',name:'API'}]},
 {id:'beta',name:'Beta',environments:[],health:'HEALTHY',resources:[{id:'web',name:'Web'}]},
] as unknown as Project[];

test('world locations are stable and verified graph edges resolve to islands',()=>{
 assert.deepEqual(islandPositions(projects),islandPositions(projects));
 const edges=sceneEdges(projects,[{id:'api:web',source:'api',target:'web',kind:'DEPENDS_ON',provenance:'compose'}],false);
 assert.equal(edges.length,1);
 assert.notDeepEqual(edges[0].from,edges[0].to);
});
