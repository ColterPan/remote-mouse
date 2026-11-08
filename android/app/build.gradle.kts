// app/build.gradle.kts — how the Remote Mouse Android app is built.
//
// Key ideas:
//  * The phone UI is NOT duplicated here: the web remote in pc/remote_mouse/web
//    is copied into the APK at build time (task `copyWebAssets`). One UI, two hosts.
//  * Release signing secrets are read from ENVIRONMENT VARIABLES only (set by
//    GitHub Actions from encrypted secrets, or by you locally). They are never
//    stored in this repository.

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val webAssetsDir = layout.buildDirectory.dir("generated/webAssets")

android {
    namespace = "io.github.colterpan.remotemouse"
    compileSdk = 35

    defaultConfig {
        applicationId = "io.github.colterpan.remotemouse"
        minSdk = 26 // Android 8.0+
        targetSdk = 35
        versionCode = 2
        versionName = "1.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    signingConfigs {
        create("release") {
            val keystore = System.getenv("RM_KEYSTORE_FILE")
            if (keystore != null) {
                storeFile = file(keystore)
                storePassword = System.getenv("RM_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("RM_KEY_ALIAS")
                keyPassword = System.getenv("RM_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            // Kept off on purpose: the app is small, and no shrinking means no
            // risk of R8 stripping something the WebView bridge needs.
            isMinifyEnabled = false
            signingConfig = if (System.getenv("RM_KEYSTORE_FILE") != null) {
                signingConfigs.getByName("release")
            } else {
                null // unsigned locally unless you provide the keystore env vars
            }
        }
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    sourceSets {
        getByName("main").assets.srcDir(webAssetsDir)
    }

    lint {
        abortOnError = true
        warningsAsErrors = false
    }
}

// Copy the shared web remote into the APK's assets.
val copyWebAssets by tasks.registering(Sync::class) {
    from(rootProject.file("../pc/remote_mouse/web"))
    into(webAssetsDir)
}
tasks.named("preBuild") { dependsOn(copyWebAssets) }

dependencies {
    implementation("androidx.activity:activity-ktx:1.9.3")
    implementation("androidx.webkit:webkit:1.12.1")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.journeyapps:zxing-android-embedded:4.3.0")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303") // real org.json for JVM unit tests
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    testImplementation("com.squareup.okhttp3:okhttp-tls:4.12.0")

    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test:runner:1.6.2")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.6.1")
    androidTestImplementation("androidx.test.espresso:espresso-web:3.6.1")
}
