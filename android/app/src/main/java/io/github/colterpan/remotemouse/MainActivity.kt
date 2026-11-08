package io.github.colterpan.remotemouse

import android.annotation.SuppressLint
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.WindowManager
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.webkit.WebViewAssetLoader
import androidx.webkit.WebViewCompat
import androidx.webkit.WebViewFeature
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions

/**
 * MainActivity — the whole app is one screen: a WebView showing the remote.
 *
 *  - The remote UI (HTML/CSS/JS) is bundled in the APK and served from the
 *    virtual address https://appassets.androidplatform.net/static/ by
 *    WebViewAssetLoader — no network needed to show it, no certificate warnings.
 *  - The page talks to native code through NativeBridge (pinned connection to
 *    your PC, QR scanning, saved PCs).
 *  - While on screen we hold a low-latency Wi-Fi lock and keep the screen on.
 */
class MainActivity : ComponentActivity(), NativeBridge.Actions {

    private lateinit var webView: WebView
    private lateinit var bridge: NativeBridge
    private lateinit var session: RemoteSession
    private lateinit var wifi: LowLatencyWifi

    private val scanLauncher = registerForActivityResult(ScanContract()) { result ->
        bridge.onScanned(result.contents)
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (!WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) {
            Toast.makeText(this, R.string.webview_too_old, Toast.LENGTH_LONG).show()
            finish()
            return
        }

        val store = PcStore(this)
        bridge = NativeBridge(store, this)
        session = RemoteSession(store, PcDiscovery(this), bridge)
        bridge.session = session
        wifi = LowLatencyWifi(this)
        setKeepAwake(true)

        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        webView = WebView(this).apply {
            setBackgroundColor(getColor(R.color.background))
            settings.javaScriptEnabled = true
            settings.domStorageEnabled = true // remembers your settings
            settings.allowFileAccess = false
            settings.allowContentAccess = false
            settings.setSupportZoom(false)
            settings.textZoom = 100
        }

        val assets = WebViewAssetLoader.Builder()
            .addPathHandler("/static/", WebViewAssetLoader.AssetsPathHandler(this))
            .build()
        webView.webViewClient = object : WebViewClient() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                assets.shouldInterceptRequest(request.url)

            // The app never navigates anywhere else.
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest) = true

            // Android may kill the WebView's renderer to free memory while the
            // app is in the background. Instead of crashing, rebuild the screen.
            override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                session.disconnect()
                recreate()
                return true
            }
        }
        // Needed for the page's confirm() dialogs (e.g. "Forget this PC?").
        webView.webChromeClient = WebChromeClient()

        WebViewCompat.addWebMessageListener(webView, BRIDGE_NAME, setOf(APP_ORIGIN)) { _, message, origin, isMainFrame, reply ->
            if (isMainFrame && origin == Uri.parse(APP_ORIGIN)) bridge.onPageMessage(message.data, reply)
        }

        setContentView(webView)
        webView.loadUrl("$APP_ORIGIN/static/index.html")
        handleDebugIntent(intent)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        handleDebugIntent(intent)
    }

    override fun onResume() {
        super.onResume()
        wifi.acquire()
    }

    override fun onPause() {
        wifi.release()
        super.onPause()
    }

    override fun onDestroy() {
        if (::session.isInitialized) session.disconnect()
        if (::webView.isInitialized) webView.destroy()
        super.onDestroy()
    }

    // --- NativeBridge.Actions -------------------------------------------------

    override fun startScan() {
        scanLauncher.launch(
            ScanOptions()
                .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
                .setPrompt(getString(R.string.scan_prompt))
                .setBeepEnabled(false)
                .setOrientationLocked(false),
        )
    }

    override fun setKeepAwake(on: Boolean) {
        runOnUiThread {
            if (on) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
            else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }
    }

    /**
     * DEBUG BUILDS ONLY — lets automated tests drive the app over adb:
     *   am start … --es rm_pair_link "<pairing link>"   pair without the camera
     *   am start … --es rm_set_host "10.9.9.9"          fake an IP change
     * Release builds ignore these completely.
     */
    private fun handleDebugIntent(intent: Intent?) {
        if (!BuildConfig.DEBUG || intent == null) return
        intent.getStringExtra("rm_pair_link")?.let { bridge.onScanned(it) }
        intent.getStringExtra("rm_set_host")?.let { host ->
            val store = PcStore(this)
            store.lastId()?.let { id -> store.get(id)?.let { store.save(it.copy(host = host)) } }
            bridge.sendPcs()
        }
    }

    private companion object {
        const val APP_ORIGIN = "https://appassets.androidplatform.net"
        const val BRIDGE_NAME = "RemoteMouseNative"
    }
}
