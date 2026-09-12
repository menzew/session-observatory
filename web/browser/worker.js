// Module worker: the accounting engine and all imported text stay off the UI thread.
let engine;
let queue = Promise.resolve();
async function initialize(assets) {
  const bytes = name => Uint8Array.from(atob(assets[name]), c => c.charCodeAt(0));
  // This data-URL worker has an opaque origin. blob:null modules cannot be
  // imported from it on a public HTTPS page; embedded data modules work in
  // both hosted and file:// editions without network access.
  const moduleURL = name => 'data:text/javascript;base64,' + assets[name];
  // Runtime fetches can only resolve these embedded resources. There is no network fallback.
  globalThis.fetch = async input => {
    const url = typeof input === 'string' ? input : (input.url || String(input));
    const name = url === 'https://offline.invalid/python_stdlib.zip' ? 'python_stdlib.zip'
      : url === 'https://offline.invalid/pyodide.asm.wasm' ? 'pyodide.asm.wasm' : null;
    if (!name) throw new Error('Network access is disabled.');
    return new Response(bytes(name), {headers:{'Content-Type':name.endsWith('.wasm')?'application/wasm':'application/octet-stream'}});
  };
  const loaderURL = moduleURL('pyodide.mjs'), runtimeURL = moduleURL('pyodide.asm.mjs');
  const {loadPyodide} = await import(loaderURL);
  const {default:create} = await import(runtimeURL);
  engine = await loadPyodide({indexURL:'https://offline.invalid/',
    stdLibURL:'https://offline.invalid/python_stdlib.zip',
    lockFileContents:JSON.parse(new TextDecoder().decode(bytes('pyodide-lock.json'))),
    createPyodideModule:options => create({...options, wasmBinary:bytes('pyodide.asm.wasm')}),
    stdout:()=>{}, stderr:()=>{}});
  engine.FS.mkdirTree('/home/pyodide/engine');
  for (const name of ['__init__.py','ledger.py','analytics.py','costs.py','limits.py','demo.py']) {
    engine.FS.writeFile('/home/pyodide/engine/'+name, bytes('engine/'+name));
  }
  engine.FS.writeFile('/home/pyodide/bridge.py', bytes('bridge.py'));
  engine.runPython('from bridge import request');
}
self.onmessage = ({data:message}) => {
  queue = queue.then(async () => {
    try {
      if (message.assets) {await initialize(message.assets); self.postMessage({id:message.id,value:{ready:true}});return;}
      engine.globals.set('_browser_request', JSON.stringify({path:message.path,data:message.data}));
      let result;
      try {result = JSON.parse(engine.runPython('request(_browser_request)'));}
      finally {engine.globals.delete('_browser_request');}
      self.postMessage({id:message.id,...result});
    } catch {
      self.postMessage({id:message.id,error:'The offline engine could not complete this operation. Use a recent Chrome or Edge browser. No data was sent anywhere.'});
    }
  });
};
