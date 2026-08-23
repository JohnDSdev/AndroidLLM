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
        versionCode = 2
        versionName = "0.2.0"

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

    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
}
