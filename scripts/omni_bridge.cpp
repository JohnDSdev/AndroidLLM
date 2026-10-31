// Experimental CPU-only multimodal inference bridge for llama.cpp b12003.
// Images (stb_image) and sound (miniaudio) decoded by libmtmd.
// Each request owns independent model/context memory; no shared mutable model globals.
#include <jni.h>
#include <string>
#include <algorithm>
#include <memory>
#include <stdexcept>
#include "llama.h"
#include "common.h"
#include "chat.h"
#include "mtmd.h"
#include "mtmd-helper.h"

namespace {
struct AutoJString {
    JNIEnv * env;
    jstring str;
    const char * data;
    AutoJString(JNIEnv * e, jstring s): env(e), str(s), data(s ? e->GetStringUTFChars(s,nullptr) : nullptr) {}
    ~AutoJString(){if(data)env->ReleaseStringUTFChars(str,data);}
    std::string value() const {return data ? data : "";}
};
jstring answer(JNIEnv *env, const std::string &text) { return env->NewStringUTF(text.c_str()); }
std::string run(const std::string & model_path,const std::string &mmproj_path,
                const std::string &media_path,const std::string &prompt,int max_tokens) {
    if(model_path.empty() || mmproj_path.empty() || media_path.empty())
        throw std::runtime_error("Choose model, projector (mmproj GGUF), and image/audio file.");
    llama_backend_init();
    auto model = std::unique_ptr<llama_model,decltype(&llama_model_free)>(
        llama_model_load_from_file(model_path.c_str(),[] {
            llama_model_params p=llama_model_default_params();p.n_gpu_layers=0;return p;
        }()), llama_model_free);
    if(!model) throw std::runtime_error("Cannot load text model GGUF.");
    auto params=llama_context_default_params();
    params.n_ctx=4096;
    params.n_batch=512;
    params.n_ubatch=512;
    params.n_threads=4;
    params.n_threads_batch=4;
    auto ctx=std::unique_ptr<llama_context,decltype(&llama_free)>(
        llama_init_from_model(model.get(),params),llama_free);
    if(!ctx)throw std::runtime_error("Cannot create llama.cpp context.");
    auto mp=mtmd_context_params_default();
    mp.use_gpu=false;mp.n_threads=4;
    mp.batch_max_tokens=512;
    auto mm=std::unique_ptr<mtmd_context,decltype(&mtmd_free)>(
        mtmd_init_from_file(mmproj_path.c_str(),model.get(),mp), mtmd_free);
    if(!mm)throw std::runtime_error("Multimodal projector failed to load; check the model and mmproj pair.");
    auto media=mtmd_helper_bitmap_init_from_file(mm.get(),media_path.c_str(),false,mtmd_helper_init_opt_default());
    if(!media.bitmap)throw std::runtime_error("Cannot decode image/audio. Use JPEG, PNG, WAV, MP3 or FLAC.");
    auto bitmap=std::unique_ptr<mtmd_bitmap,decltype(&mtmd_bitmap_free)>(media.bitmap,mtmd_bitmap_free);
    // Video files are not accepted by this lightweight bridge: no ffmpeg binary is bundled.
    if(media.video_ctx)throw std::runtime_error("Video processing is not bundled in this build.");

    auto templates=common_chat_templates_init(model.get(),"");
    common_chat_msg msg;msg.role="user";
    const std::string marker=mtmd_default_marker();
    msg.content=std::string("Respond with plain text only, without audio generation. ") +
        (prompt.empty() ? "Describe this media." : prompt) + "\n" + marker;
    std::string formatted=common_chat_format_single(templates.get(),{},msg,true,false);
    auto position=formatted.find(marker);
    if(position==std::string::npos)throw std::runtime_error("The model chat template didn't retain the media marker.");
    std::string first=formatted.substr(0,position),last=formatted.substr(position+marker.size());
    mtmd_input_text first_text{first.c_str(),first.size(),false,true};
    mtmd_input_text last_text{last.c_str(),last.size(),false,true};
    mtmd_input_part part0{&first_text,nullptr};
    mtmd_input_part part1{nullptr,bitmap.get()};
    mtmd_input_part part2{&last_text,nullptr};
    const mtmd_input_part * allparts[]={&part0,&part1,&part2};
    auto chunks=std::unique_ptr<mtmd_input_chunks,decltype(&mtmd_input_chunks_free)>(
        mtmd_input_chunks_init(),mtmd_input_chunks_free);
    if(mtmd_tokenize_from_parts(mm.get(),chunks.get(),allparts,3,true)!=0)
        throw std::runtime_error("Unable to tokenize multimodal input.");
    llama_pos position_after=0;
    int ret=mtmd_helper_eval_chunks(mm.get(),ctx.get(),chunks.get(),0,0,512,true,&position_after);
    if(ret!=0)throw std::runtime_error("Multimodal prompt evaluation failed ("+std::to_string(ret)+").");
    auto sampler=std::unique_ptr<llama_sampler,decltype(&llama_sampler_free)>(
        llama_sampler_init_greedy(),llama_sampler_free);
    common_batch batch(ctx.get());
    std::string out;
    const llama_vocab *vocab=llama_model_get_vocab(model.get());
    for(int i=0;i<std::clamp(max_tokens,1,256);i++) {
        llama_token token=llama_sampler_sample(sampler.get(),ctx.get(),-1);
        if(llama_vocab_is_eog(vocab,token))break;
        out+=common_token_to_piece(ctx.get(),token);
        batch.clear();batch.add(token,position_after++,0,true);
        if(llama_process(ctx.get(),LLAMA_PROCESS_TYPE_DECODE,batch.get())!=0)
            throw std::runtime_error("Decode failed after generation.");
    }
    return out.empty() ? "[No text generated]" : out;
}
}
extern "C" JNIEXPORT jstring JNICALL
Java_com_johndsdev_androidllm_MultimodalBridge_infer(
    JNIEnv* env,jclass,jstring model,jstring projector,jstring media,jstring prompt,jint maxTokens) {
    try {
        AutoJString a(env,model),b(env,projector),c(env,media),d(env,prompt);
        return answer(env,run(a.value(),b.value(),c.value(),d.value(),maxTokens));
    } catch(const std::exception &e) {
        return answer(env,std::string("Multimodal inference error: ")+e.what());
    } catch(...) {
        return answer(env,"Multimodal inference failed (unknown native error).");
    }
}
