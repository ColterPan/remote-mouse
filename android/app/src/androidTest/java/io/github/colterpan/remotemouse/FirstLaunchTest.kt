package io.github.colterpan.remotemouse

import androidx.test.espresso.web.assertion.WebViewAssertions.webMatches
import androidx.test.espresso.web.sugar.Web.onWebView
import androidx.test.espresso.web.webdriver.DriverAtoms.findElement
import androidx.test.espresso.web.webdriver.DriverAtoms.getText
import androidx.test.espresso.web.webdriver.Locator
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.hamcrest.Matchers.containsString
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/**
 * Runs ON A DEVICE (emulator in CI, or a real phone over adb):
 * a fresh install opens the bundled remote UI, and the native bridge answers,
 * so the "Add your PC" pairing screen appears.
 *
 *   ./gradlew connectedDebugAndroidTest
 */
@RunWith(AndroidJUnit4::class)
class FirstLaunchTest {
    @get:Rule
    val activity = ActivityScenarioRule(MainActivity::class.java)

    @Test
    fun freshInstallShowsAddYourPc() {
        // pair-title is only set to "Add your PC" after the native bridge
        // replied with an empty PC list — so this proves both sides work.
        Thread.sleep(1500)
        onWebView()
            .withElement(findElement(Locator.ID, "pair-title"))
            .check(webMatches(getText(), containsString("Add your PC")))
    }

    @Test
    fun scanButtonIsOffered() {
        Thread.sleep(1500)
        onWebView()
            .withElement(findElement(Locator.ID, "pair-scan"))
            .check(webMatches(getText(), containsString("Scan QR code")))
    }
}
