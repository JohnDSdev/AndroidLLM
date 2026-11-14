// Edge0's independently linked CPU runtime. GGUF models continue using llama.cpp.
#include <jni.h>
#include <edge0/generation.h>
#include <android/log.h>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
struct State {
    std::optional<edge0::RuntimeReference> runtime;
    edge0::ModelReference model;
    edge0::SessionReference session;
    std::mutex cancel_mutex;
    std::optional<edge0::CancelToken> cancel;
};

State& state(jlong handle) {
    if (!handle) throw std::runtime_error("Edge0 runtime is closed");
    return *reinterpret_cast<State*>(handle);
}

template<typename T>
T checked(const edge0::Result<T>& r) {
    if (!r) throw std::runtime_error(r.error().message);
    return r.value();
}

std::string string_value(JNIEnv* env, jstring value) {
    if (!value) return {};
    // Java UTF-8 bytes handle supplementary characters (unlike GetStringUTFChars).
    auto string_class = env->FindClass("java/lang/String");
    auto encoding = env->NewStringUTF("UTF-8");
    auto method = env->GetMethodID(string_class, "getBytes", "(Ljava/lang/String;)[B");
    auto arr = static_cast<jbyteArray>(env->CallObjectMethod(value, method, encoding));
    if (!arr || env->ExceptionCheck()) return {};
    const auto n = env->GetArrayLength(arr);
    std::string result(static_cast<size_t>(n), '\0');
    if (n) env->GetByteArrayRegion(arr, 0, n, reinterpret_cast<jbyte*>(&result[0]));
    env->DeleteLocalRef(arr);
    env->DeleteLocalRef(encoding);
    env->DeleteLocalRef(string_class);
    return result;
}

void throw_java(JNIEnv* env, const std::exception& e) {
    env->ThrowNew(env->FindClass("java/lang/IllegalStateException"), e.what());
}

void unload(State& s) {
    if (s.session) { checked(edge0::release_session(s.session)); s.session.reset(); }
    if (s.model) { checked(edge0::unload_model(s.model)); s.model.reset(); }
    std::lock_guard<std::mutex> lock(s.cancel_mutex);
    s.cancel.reset();
}

jbyteArray byte_array(JNIEnv* env, const std::string& str) {
    auto data = env->NewByteArray(static_cast<jsize>(str.size()));
    if (data && !str.empty()) {
        env->SetByteArrayRegion(data, 0, static_cast<jsize>(str.size()),
                                reinterpret_cast<const jbyte*>(str.data()));
    }
    return data;
}
}

extern "C" JNIEXPORT jlong JNICALL
Java_com_johndsdev_androidllm_Edge0Runtime_nativeCreate(JNIEnv*, jobject) {
    return reinterpret_cast<jlong>(new State());
}

extern "C" JNIEXPORT jlong JNICALL
Java_com_johndsdev_androidllm_Edge0Runtime_nativeLoad(
        JNIEnv* env, jobject, jlong handle, jstring directory) {
    try {
        auto& s = state(handle);
        unload(s);
        if (!s.runtime) {
            edge0::RuntimeOptions options;
            for (const auto& device : edge0::query_capabilities().devices) {
                if (device.backend == "cpu") { options.devices = {device.name}; break; }
            }
            if (options.devices.empty()) throw std::runtime_error("Edge0 CPU backend unavailable");
            options.log_receiver = [](edge0::LogLevel, const std::string& message) {
                __android_log_write(ANDROID_LOG_INFO, "AndroidLLM-Edge0", message.c_str());
            };
            s.runtime = checked(edge0::open_runtime(options));
        }
        edge0::LoadOverrides overrides;
        overrides.device = s.runtime->available_devices().front();
        auto configuration = checked(edge0::resolve_load_configuration(
            *s.runtime, string_value(env, directory), overrides));
        s.model = checked(edge0::load_model(*s.runtime, configuration));
        auto info = checked(edge0::query_model(s.model));
        s.session = checked(edge0::create_session(s.model));
        return static_cast<jlong>(info.context);
    } catch (const std::exception& e) { throw_java(env, e); return 0; }
}

extern "C" JNIEXPORT void JNICALL
Java_com_johndsdev_androidllm_Edge0Runtime_nativeReset(
        JNIEnv* env, jobject, jlong handle) {
    try { checked(edge0::reset_conversation(state(handle).session)); }
    catch (const std::exception& e) { throw_java(env, e); }
}

extern "C" JNIEXPORT void JNICALL
Java_com_johndsdev_androidllm_Edge0Runtime_nativePrepare(
        JNIEnv* env, jobject, jlong handle) {
    try {
        auto& s = state(handle);
        auto token = checked(edge0::create_cancel_token(*s.runtime));
        std::lock_guard<std::mutex> lock(s.cancel_mutex);
        s.cancel = std::move(token);
    } catch (const std::exception& e) { throw_java(env, e); }
}

extern "C" JNIEXPORT void JNICALL
Java_com_johndsdev_androidllm_Edge0Runtime_nativeCancel(
        JNIEnv*, jobject, jlong handle) {
    if (!handle) return;
    auto& s = state(handle);
    std::lock_guard<std::mutex> lock(s.cancel_mutex);
    if (s.cancel) edge0::request_cancel(*s.cancel);
}

extern "C" JNIEXPORT jdouble JNICALL
Java_com_johndsdev_androidllm_Edge0Runtime_nativeGenerate(
        JNIEnv* env, jobject, jlong handle,
        jobjectArray roles, jobjectArray contents, jboolean thinking,
        jdouble temperature, jobject callback) {
    try {
        auto& s = state(handle);
        edge0::CancelToken token;
        {
            std::lock_guard<std::mutex> lock(s.cancel_mutex);
            if (!s.cancel) throw std::runtime_error("Missing Edge0 cancellation token");
            token = *s.cancel;
        }
        const auto count = env->GetArrayLength(roles);
        if (count != env->GetArrayLength(contents)) {
            throw std::runtime_error("Edge0 message role/content lengths differ");
        }
        std::vector<edge0::TextMessage> messages;
        messages.reserve(count);
        for (jsize i = 0; i < count; ++i) {
            auto role = static_cast<jstring>(env->GetObjectArrayElement(roles, i));
            auto text = static_cast<jstring>(env->GetObjectArrayElement(contents, i));
            messages.push_back({string_value(env, role), string_value(env, text)});
            env->DeleteLocalRef(role);
            env->DeleteLocalRef(text);
        }
        edge0::GenerationOverrides overrides;
        overrides.thinking = static_cast<bool>(thinking);
        overrides.temperature = static_cast<double>(temperature);
        const auto config = checked(edge0::resolve_generation_configuration(s.model, overrides));
        auto cls = env->GetObjectClass(callback);
        auto method = env->GetMethodID(cls, "onEvent", "(I[B)V");
        if (!method) throw std::runtime_error("Edge0 callback method missing");
        auto response = checked(edge0::generate(
            s.session, messages, config, {},
            [&](const edge0::OutputEvent& event) -> std::optional<edge0::Error> {
                if (event.kind == edge0::OutputKind::answer ||
                    event.kind == edge0::OutputKind::reasoning) {
                    auto bytes = byte_array(env, event.text);
                    env->CallVoidMethod(callback, method,
                        event.kind == edge0::OutputKind::reasoning ? 1 : 0, bytes);
                    env->DeleteLocalRef(bytes);
                    if (env->ExceptionCheck()) {
                        env->ExceptionClear();
                        return edge0::Error{
                            edge0::ErrorCategory::invalid_argument,
                            "AndroidLLM Edge0 output callback failed"};
                    }
                }
                return {};
            }, &token));
        env->DeleteLocalRef(cls);
        {
            std::lock_guard<std::mutex> lock(s.cancel_mutex);
            s.cancel.reset();
        }
        if (response.error) throw std::runtime_error(response.error->message);
        if (!response.state_valid) throw std::runtime_error("Edge0 session became invalid; reload the model");
        if (response.stop_reason == edge0::StopReason::failed) {
            throw std::runtime_error("Edge0 generation failed");
        }
        return response.request_summary.decode_tokens_per_second.value_or(0.0);
    } catch (const std::exception& e) { throw_java(env, e); return 0; }
}

extern "C" JNIEXPORT void JNICALL
Java_com_johndsdev_androidllm_Edge0Runtime_nativeUnload(
        JNIEnv* env, jobject, jlong handle) {
    try { unload(state(handle)); }
    catch (const std::exception& e) { throw_java(env, e); }
}
