// SSL Pinning Bypass for 东方财富 APP
// 绕过 OkHttp3 和系统级证书固定

Java.perform(function() {
    console.log("[*] SSL Pinning Bypass loaded");

    // 1. 绕过 OkHttp3 CertificatePinner
    try {
        var CertificatePinner = Java.use("okhttp3.CertificatePinner");
        CertificatePinner.check.overload("java.lang.String", "java.util.List").implementation = function(hostname, peerCertificates) {
            console.log("[+] Bypassing OkHttp3 pinning for: " + hostname);
            return;
        };
        console.log("[*] OkHttp3 CertificatePinner hooked");
    } catch(e) {
        console.log("[-] OkHttp3 not found: " + e);
    }

    // 2. 绕过 TrustManagerImpl (Android系统)
    try {
        var TrustManagerImpl = Java.use("com.android.org.conscrypt.TrustManagerImpl");
        TrustManagerImpl.verifyChain.implementation = function(untrustedChain, trustAnchorChain, host, clientAuth, ocspData, tlsSctData) {
            console.log("[+] Bypassing TrustManagerImpl for: " + host);
            return untrustedChain;
        };
        console.log("[*] TrustManagerImpl hooked");
    } catch(e) {
        console.log("[-] TrustManagerImpl not found: " + e);
    }

    // 3. 绕过 SSLContext
    try {
        var X509TrustManager = Java.use("javax.net.ssl.X509TrustManager");
        var SSLContext = Java.use("javax.net.ssl.SSLContext");
        
        var TrustManager = Java.registerClass({
            name: "com.bypass.TrustManager",
            implements: [X509TrustManager],
            methods: {
                checkClientTrusted: function(chain, authType) {},
                checkServerTrusted: function(chain, authType) {},
                getAcceptedIssuers: function() { return []; }
            }
        });

        var TrustManagers = [TrustManager.$new()];
        var ctx = SSLContext.getInstance("TLS");
        ctx.init(null, TrustManagers, null);
        SSLContext.getInstance("TLS").init(null, TrustManagers, null);
        console.log("[*] SSLContext hooked");
    } catch(e) {
        console.log("[-] SSLContext hook failed: " + e);
    }

    // 4. 绕过 HttpsURLConnection
    try {
        var HttpsURLConnection = Java.use("javax.net.ssl.HttpsURLConnection");
        HttpsURLConnection.setDefaultSSLSocketFactory.implementation = function(sslSocketFactory) {
            console.log("[+] Bypassing HttpsURLConnection SSLSocketFactory");
        };
        HttpsURLConnection.setHostnameVerifier.implementation = function(hostnameVerifier) {
            console.log("[+] Bypassing HttpsURLConnection HostnameVerifier");
        };
        console.log("[*] HttpsURLConnection hooked");
    } catch(e) {
        console.log("[-] HttpsURLConnection not found: " + e);
    }

    // 5. 绕过 WebViewClient
    try {
        var WebViewClient = Java.use("android.webkit.WebViewClient");
        WebViewClient.onReceivedSslError.implementation = function(view, handler, error) {
            console.log("[+] Bypassing WebView SSL error");
            handler.proceed();
        };
        console.log("[*] WebViewClient hooked");
    } catch(e) {
        console.log("[-] WebViewClient not found: " + e);
    }

    console.log("[*] SSL Pinning Bypass complete!");
});
