// Native LFM3 Omni voice output using llama.cpp mtmd's depthformer and audio codec.
// Separate session from image/audio prompt inference; writes model-generated PCM as WAV.
#include <jni.h>
#include <string>
#include <memory>
#include <stdexcept>
#include <fstream>
#include <vector>
#include "llama.h"
#include "common.h"
#include "chat.h"
#include "mtmd.h"
#include "mtmd-helper.h"

namespace {
struct UtfString {
    JNIEnv *env; jstring value; const char *data;
    UtfString(JNIEnv* e,jstring s):env(e),value(s),data(s?e->GetStringUTFChars(s,nullptr):nullptr){}
    ~UtfString(){if(data)env->ReleaseStringUTFChars(value,data);}
    std::string str()const{return data?data:"";}
};
std::string make_voice(const std::string & modelPath, const std::string & mmprojPath,
                       const std::string & message, const std::string & wavPath) {
    if(modelPath.empty()||mmprojPath.empty()||wavPath.empty()||message.empty()) {
        throw std::runtime_error("Model, projector, speech text and output WAV path required");
    }
    llama_backend_init();
    llama_model_params mp=llama_model_default_params();
    mp.n_gpu_layers=0;
    std::unique_ptr<llama_model,decltype(&llama_model_free)> model(
        llama_model_load_from_file(modelPath.c_str(),mp),llama_model_free);
    if(!model)throw std::runtime_error("Unable to load Omni speech model");
    llama_context_params cp=llama_context_default_params();
    cp.n_ctx=4096;
    cp.n_batch=512;
    cp.n_ubatch=512;
    cp.n_threads=4;
    cp.n_threads_batch=4;
    cp.embeddings=true; // speech generator consumes hidden state from the backbone
    std::unique_ptr<llama_context,decltype(&llama_free)> context(
        llama_init_from_model(model.get(),cp),llama_free);
    if(!context)throw std::runtime_error("Unable to create speech context");

    auto mparams=mtmd_context_params_default();
    mparams.use_gpu=false;
    mparams.n_threads=4;
    std::unique_ptr<mtmd_context,decltype(&mtmd_free)> mm(
        mtmd_init_from_file(mmprojPath.c_str(),model.get(),mparams),mtmd_free);
    if(!mm)throw std::runtime_error("Unable to load matching mmproj");
    if(mtmd_gen_audio_get_info(mm.get()).type==MTMD_GEN_AUDIO_TYPE_NONE)
        throw std::runtime_error("This mmproj doesn't support model-native audio output");

    auto templates=common_chat_templates_init(model.get(),"");
    std::string formatted=common_chat_get_tts_prompt(templates.get(),message,"","");
    if(formatted.empty())formatted=message;
    mtmd_helper::gen_audio gen;
    gen.init(context.get(),mm.get());
    mtmd_helper_gen_audio_inp input=mtmd_helper_gen_audio_inp_default();
    input.seq_id=0;
    input.prompt=formatted.c_str();
    input.prompt_len=formatted.size();
    input.top_k=40;
    input.top_p=0.95f;
    if(gen.set_input(&input)!=0)throw std::runtime_error("Omni speech prompt not accepted");
    for(int n=0;n<4096;n++){
        int32_t ret=gen.step_prompt(512);
        if(ret<0)throw std::runtime_error("Omni speech prompt evaluation failed");
        if(ret==0)break;
        if(n==4095)throw std::runtime_error("Audio prompt exceeded processing limit");
    }
    std::unique_ptr<llama_sampler,decltype(&llama_sampler_free)> sampler(
        llama_sampler_init_greedy(),llama_sampler_free);
    auto sample=[&]()->llama_token{return llama_sampler_sample(sampler.get(),context.get(),-1);};
    llama_token sampled=gen.next_is_text()?sample():LLAMA_TOKEN_NULL;
    const float *hidden=llama_get_embeddings_ith(context.get(),-1);
    if(!hidden)throw std::runtime_error("The speech backbone did not return hidden states");
    bool stop=false;
    int produced=0;
    for(int frame=0;frame<320&&!stop;frame++){
        const float* next=nullptr;
        if(gen.step_gen(sampled,hidden,&next,&stop)!=0)
            throw std::runtime_error("Omni depthformer/audio codec failed on frame "+std::to_string(frame));
        if(!next)break;
        hidden=next;
        produced++;
        sampled=gen.next_is_text()?sample():LLAMA_TOKEN_NULL;
    }
    if(produced==0)throw std::runtime_error("Omni did not produce audio frames");
    int32_t sample_rate=0;
    const char *wav=nullptr;
    size_t bytes=0;
    int64_t samples=0;
    if(gen.get_output(&sample_rate,&wav,&bytes,&samples)!=0||!wav||bytes<44)
        throw std::runtime_error("Omni audio decoder returned no WAV");
    std::ofstream out(wavPath,std::ios::binary|std::ios::trunc);
    if(!out)throw std::runtime_error("Could not open WAV output");
    out.write(wav,static_cast<std::streamsize>(bytes));
    out.flush();
    if(!out)throw std::runtime_error("Failed writing Omni WAV");
    return wavPath;
}
}
extern "C" JNIEXPORT jstring JNICALL
Java_com_johndsdev_androidllm_MultimodalBridge_synthesizeNativeSpeech(
    JNIEnv* env,jclass,jstring model,jstring mmproj,jstring words,jstring outputFile) {
    try {
        UtfString m(env,model),p(env,mmproj),w(env,words),o(env,outputFile);
        std::string res=make_voice(m.str(),p.str(),w.str(),o.str());
        return env->NewStringUTF(res.c_str());
    }catch(const std::exception &e){
        std::string msg=std::string("ERROR: ")+e.what();
        return env->NewStringUTF(msg.c_str());
    }catch(...){
        return env->NewStringUTF("ERROR: Unknown native speech synthesis failure");
    }
}
