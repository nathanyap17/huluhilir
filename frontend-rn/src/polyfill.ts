import 'react-native-url-polyfill/auto';
// @ts-ignore
import { encode, decode } from 'base-64';

const g = globalThis as any;

if (!g.btoa) {
    g.btoa = encode;
}
if (!g.atob) {
    g.atob = decode;
}

if (typeof g.TextEncoder === 'undefined') {
    const { TextEncoder, TextDecoder } = require('fast-text-encoding');
    g.TextEncoder = TextEncoder;
    g.TextDecoder = TextDecoder;
}

if (typeof process !== 'undefined' && typeof (process as any).emitWarning !== 'function') {
    (process as any).emitWarning = function(warning: any) {
        console.warn(warning);
    };
} else if (typeof process === 'undefined') {
    g.process = {
        env: {},
        emitWarning: function(warning: any) { console.warn(warning); }
    };
}
