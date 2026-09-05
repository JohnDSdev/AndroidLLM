plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.jetbrains.kotlin.android)
}

android {
    namespace = "com.johndsdev.androidllm"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.johndsdev.androidllm"
        minSdk = 33
        targetSdk = 36
        versionCode = 17
        versionName = "0.8.0"

        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    signingConfigs {
        create("development") {
            storeFile = rootProject.file("signing/androidllm-dev.keystore")
            storePassword = "androidllm-dev"
            keyAlias = "androidllm"
            keyPassword = "androidllm-dev"
        }
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("development")
        }
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("development")
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    testOptions { unitTests.isIncludeAndroidResources = true }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlin {
        jvmToolchain(17)
        compileOptions {
            targetCompatibility = JavaVersion.VERSION_17
        }
    }
}

dependencies {
    implementation(project(":llamaLib"))
    implementation(libs.bundles.androidx)
    implementation(libs.material)
    implementation(libs.kotlinx.coroutines.android)
    implementation("androidx.recyclerview:recyclerview:1.4.0")
    implementation("androidx.drawerlayout:drawerlayout:1.2.0")
    implementation("io.noties.markwon:core:4.6.2")

    testImplementation(libs.junit)
    testImplementation("org.robolectric:robolectric:4.16.1")
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
}
