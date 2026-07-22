/*
 * frida_recon_em.js  —  East Money APP recon hook
 *
 * Disables SSL pinning, enables WebView debugging (so Chrome DevTools can connect),
 * and logs every HTTP request's URL/headers and every WebView.loadUrl to stdout.
 *
 * Usage from host:
 *   frida -U -f com.eastmoney.android.berlin -l scripts/frida_recon_em.js -o data/recon/frida.log --runtime=v8
 *
 * Output is appended to data/recon/frida.log.  While the script runs the operator
 * performs the action under investigation in the East Money APP and we capture
 * all network traffic at the Java layer plus WebView navigation.
 */

'use strict';

/* ---------------------------------------------------------------- logging helpers */
function tag(scope){return "=== " + scope;}

/* Append structured JSON lines so it's trivially post-processable in python. */
function emit(obj){
    obj.t = Date.now();
    try {
        send(obj);   // frida message channel, picked up by `frida -o`
    } catch(e){ /* ignore */ }
    console.log(JSON.stringify(obj));   /* also stream to console for live watch */
}

/* ------------------------------------------------------ 0) General SSL bypass --- */

function disableSSL_pinning(){
    // Strategy 1: hook X509TrustManagerExtensions + pass-through TrustManager
    Java.perform(function(){
        try {
            var X509TrustManager = Java.use('javax.net.ssl.X509TrustManager');
            var TrustManager = Java.registerClass({
                name: 'org.recon.NaiveTrustManager',
                implements: [X509TrustManager],
                methods: {
                    checkClientTrusted: function(){},
                    checkServerTrusted: function(){},
                    getAcceptedIssuers: function(){ return []; }
                }
            });
            var SSLContext = Java.use('javax.net.ssl.SSLContext');
            var TrustManagerArray = Java.array('javax.net.ssl.TrustManager', [TrustManager.$new()]);
            SSLContext.init.overload('javax.net.ssl.KeyManager[]','javax.net.ssl.TrustManager[]','java.security.SecureRandom').implementation = function(km,tm,sr){
                console.log(tag("SSL") + " SSLContext.init -- replacing TrustManager");
                return this.init(km, TrustManagerArray, sr);
            };
            console.log(tag("OK") + " SSL pinning bypass via SSLContext installed");
        } catch(e){
            console.log(tag("FAIL") + " SSLContext hook: " + e);
        }

        // Strategy 2: okhttp3.CertificatePinner - common in OkHttp apps
        try {
            var Pinner = Java.use('okhttp3.CertificatePinner');
            Pinner.check.overload('java.lang.String','java.util.List').implementation = function(/*host,peer*/){
                console.log(tag("SSL") + " okhttp3.CertificatePinner.check skipped");
                /* silently allow */
            };
            if (Pinner.check$okhttp) {
                Pinner.check$okhttp.implementation = function(){ console.log(tag("SSL")+" CertificatePinner.check$okhttp skipped"); };
            }
            console.log(tag("OK") + " okhttp3 CertificatePinner neutralized");
        } catch(e){ console.log(tag("note")+" okhttp3.CertificatePinner not present: " + e); }

        // Strategy 3: javax.net.ssl.HostnameVerifier - allow all
        try {
            var HV = Java.use('okhttp3.internal.tls.OkHostnameVerifier');
            HV.verify.overload('java.lang.String','javax.net.ssl.SSLSession').implementation = function(){ return true; };
            console.log(tag("OK") + " OkHostnameVerifier bypass installed");
        } catch(e){ /* ok */ }
    });
}

/* ------------------------------------------------------- 1) OkHttp URL + headers */

function hookOkHttp(){
    Java.perform(function(){
        try {
            var RealCall = Java.use('okhttp3.RealCall');
            RealCall.getResponseWithInterceptorChain.implementation = function(){
                try {
                    var req = this.originalRequest.value;
                    var url = req.url().toString();
                    var headers = {};
                    var hs = req.headers();
                    var sz = hs.size();
                    for (var i=0;i<sz;i++){ headers[hs.name(i)] = hs.value(i); }
                    emit({kind:"okhttp_req", url:url, method:req.method(), headers:headers, body: req.body() ? "<body>" : null});
                } catch(e){ emit({kind:"okhttp_err",err:String(e)}); }
                return this.getResponseWithInterceptorChain();
            };
            console.log(tag("OK") + " okhttp3.RealCall hooked");
        } catch(e){ console.log(tag("FAIL")+" okhttp3.RealCall: " + e); }
    });
}

/* ------------------------------------------------------ 2) HttpURLConnection ----- */

function hookUrlConnection(){
    Java.perform(function(){
        try {
            var URL = Java.use('java.net.URL');
            var HUC = Java.use('com.android.okhttp.internal.huc.HttpURLConnectionImpl');

            HUC.connect.implementation = function(){
                try {
                    emit({kind:"huc_connect", url: this.getURL().toString()});
                } catch(e){}
                return this.connect();
            };
            console.log(tag("OK") + " HttpURLConnectionImpl.connect hooked");
        } catch(e){ console.log(tag("note")+" HttpURLConnectionImpl: " + e); }
    });
}

/* --------------------------------------------------------- 3) WebView nav/debug */

function hookWebView(){
    Java.perform(function(){
        var WebView = null;
        try { WebView = Java.use('android.webkit.WebView'); }
        catch(e){ console.log(tag("FAIL")+" WebView class: "+e); return; }

        // Force enable debugging regardless of what the APP chose.
        try {
            WebView.setWebContentsDebuggingEnabled(true);
            WebView.setWebContentsDebuggingEnabled.implementation = function(b){
                console.log(tag("WebView") + " APP requested setWebContentsDebuggingEnabled(" + b + ") -> forced true");
                return this.setWebContentsDebuggingEnabled(true);
            };
            console.log(tag("OK") + " WebView.setWebContentsDebuggingEnabled true (forced)");
        } catch(e){ console.log(tag("note")+" wv.setWebContentsDebuggingEnabled: " + e); }

        // Hook every URL the WebView navigates to + its enclosing Activity
        try {
            WebView.loadUrl.overload('java.lang.String').implementation = function(url){
                emit({kind:"wv_load_url", url:url, activity: currentActivity()});
                return this.loadUrl(url);
            };
            WebView.loadUrl.overload('java.lang.String','java.util.Map').implementation = function(url,headers){
                var h = {};
                try {
                    var it = headers.entrySet().iterator();
                    while (it.hasNext()){ var e = it.next(); h[e.getKey()] = e.getValue(); }
                } catch(_){}
                emit({kind:"wv_load_url_headers", url:url, headers:h, activity: currentActivity()});
                return this.loadUrl(url, headers);
            };
            console.log(tag("OK") + " WebView.loadUrl hooked (both signatures)");
        } catch(e){ console.log(tag("note")+" loadUrl hook: " + e); }
    });
}

/* ------------------------------------------------ 4) try to obtain activity name */

var ActivityThread = null;
function currentActivity(){
    try {
        if (!ActivityThread) ActivityThread = Java.use('android.app.ActivityThread');
        var trampoline = ActivityThread.currentApplication().getApplicationContext();
        // best-effort: ask ActivityManager for focused;
        return "<n/a>";
    } catch(e){ return "<err "+e+">"; }
}

/* ----------------------------------------------------------------- 5) httpurl.readyState getter would be more reliable but keep simple */

/* --------------------------------------------------------------------- execute */

/* frida 17: top-level Java.perform is the safest entry point. */
Java.perform(function(){
    console.log(tag("BOOT") + " recon script starting in PID " + Process.id + " arch=" + Process.arch);
    disableSSL_pinning();
    hookOkHttp();
    hookUrlConnection();
    hookWebView();
    console.log(tag("READY") + " hooks installed; now perform your test in the APP");
});