// List all globals exposed by frida runtime in NATIVE default realm
console.log('=== total globals ===');
const keys = Object.keys(globalThis);
console.log('count:', keys.length);
console.log(keys.join(','));
console.log('=== process ===');
console.log('Process.enumerateModules.length:', Process.enumerateModules.length);
// Did Java binding ever exist?
try {
  console.log('globalThis.Java:', globalThis.hasOwnProperty('Java'));
  console.log('globalThis.Java:', globalThis.Java);
} catch(e) { console.log('globalThis.Java err:', e); }
// Try common Java bridge path
try {
  const Java = require('frida-java-bridge');
  console.log('require(\'frida-java-bridge\') ok:', typeof Java);
} catch(e) { console.log('require err:', e); }
// Probe ART loaded bridges from process modules
let libart = Process.findModuleByName('libart.so');
console.log('libart.so:', libart ? JSON.stringify({name: libart.name, base: libart.base.toString(), size: libart.size}) : 'NOT FOUND');
// Check if Java is injected into a 'realm' object via Java.bridge
console.log('typeof Java:', typeof Java, 'typeof Module:', typeof Module, 'typeof Script:', typeof Script);
try { console.log('Script.runtime:', Script.runtime); } catch(e) {}
try { console.log('Process.platform:', Process.platform); } catch(e) {}