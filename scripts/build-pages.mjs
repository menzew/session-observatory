// Stage only reviewed browser artifacts for the public GitHub Pages repository.
import {copyFile, mkdir, writeFile} from 'node:fs/promises';
import {dirname, join} from 'node:path';
import {fileURLToPath} from 'node:url';

const root=dirname(dirname(fileURLToPath(import.meta.url)));
const source=join(root,'dist'),site=join(source,'site');
await mkdir(site,{recursive:true});
const app='session-observatory-browser.html';
await copyFile(join(source,app),join(site,'index.html'));
for(const name of [app,app+'.sha256','browser-runtime-manifest.json']){
  await copyFile(join(source,name),join(site,name));
}
await writeFile(join(site,'.nojekyll'),'');
console.log('Staged the public browser app and offline download in dist/site/.');
