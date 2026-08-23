pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "AndroidLLM"
include(":app")
include(":llamaLib")
project(":llamaLib").projectDir = file("vendor/llama.cpp/examples/llama.android/lib")
