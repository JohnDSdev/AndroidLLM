cmake_minimum_required(VERSION 3.22.1)
project(androidllm_edge0 LANGUAGES C CXX)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
# Edge0 has its own statically linked GGML; llama.cpp remains separate.
set(MOE_BUILD_CLI OFF CACHE BOOL "" FORCE)
set(MOE_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(MOE_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(GGML_VULKAN OFF CACHE BOOL "" FORCE)
set(GGML_BACKEND_DL OFF CACHE BOOL "" FORCE)
add_subdirectory("${CMAKE_CURRENT_SOURCE_DIR}/../../../../vendor/Edge0/edge0-infer"
                 "${CMAKE_CURRENT_BINARY_DIR}/edge0-engine")
add_library(edge0_androidllm SHARED edge0_bridge.cpp)
target_link_libraries(edge0_androidllm PRIVATE edge0::edge0 android log)
