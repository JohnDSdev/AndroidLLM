plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.jetbrains.kotlin.android)
}

android {
    namespace = "com.johndsdev.androidllm"
    compileSdk = 36
    ndkVersion = "29.0.14206865"

    defaultConfig {
        applicationId = "com.johndsdev.androidllm"
        minSdk = 33
        targetSdk = 36
        versionCode = 16
        versionName = "0.7.4"

        externalNativeBuild {
            cmake { arguments += listOf("-DCMAKE_BUILD_TYPE=Release", "-DGGML_VULKAN=OFF") }
        }

        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.31.6"
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
    implementation("androidx.drawerlayout:drawerlayout:1.2.0")
    implementation("io.noties.markwon:core:4.6.2")
    implementation("androidx.documentfile:documentfile:1.0.1")

    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
}
