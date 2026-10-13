# Unit tests for the engine-agnostic rules engine in Source/IronReign/Sim.
# Build: cmake -S Tests -B <build dir> && cmake --build <build dir> -j && ctest --test-dir <build dir> --output-on-failure
cmake_minimum_required(VERSION 3.20)
project(IronReignSimTests CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE RelWithDebInfo)
endif()

set(IRON_MODULE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../Source/IronReign)
set(IRON_SIM_DIR ${IRON_MODULE_DIR}/Sim)
file(GLOB IRON_SIM_SOURCES CONFIGURE_DEPENDS ${IRON_SIM_DIR}/*.cpp)

# Stand-ins for engine parts that are still being written.
if(NOT EXISTS ${IRON_SIM_DIR}/IronBattle.cpp)
  list(APPEND IRON_SIM_SOURCES ${CMAKE_CURRENT_SOURCE_DIR}/Stubs/BattleStub.cpp)
endif()

# Mirror Unreal's constraints for the Sim folder: no exceptions, no RTTI, warnings are errors.
set(IRON_STRICT_FLAGS -fno-exceptions -fno-rtti -Wall -Wextra -Wshadow -Werror)

add_library(IronSimCore STATIC ${IRON_SIM_SOURCES})
target_include_directories(IronSimCore PUBLIC ${IRON_MODULE_DIR})
target_compile_options(IronSimCore PRIVATE ${IRON_STRICT_FLAGS})

# Unreal compiles modules as unity builds; make sure the Sim sources also compile as one translation unit.
set(IRON_UNITY_FILE ${CMAKE_CURRENT_BINARY_DIR}/IronSimUnity.cpp)
set(IRON_UNITY_CONTENT "")
foreach(Source ${IRON_SIM_SOURCES})
  string(APPEND IRON_UNITY_CONTENT "#include \"${Source}\"\n")
endforeach()
file(WRITE ${IRON_UNITY_FILE}.in "${IRON_UNITY_CONTENT}")
configure_file(${IRON_UNITY_FILE}.in ${IRON_UNITY_FILE} COPYONLY)
add_library(IronSimUnityCheck OBJECT ${IRON_UNITY_FILE})
target_include_directories(IronSimUnityCheck PRIVATE ${IRON_MODULE_DIR})
target_compile_options(IronSimUnityCheck PRIVATE ${IRON_STRICT_FLAGS})

file(GLOB IRON_TEST_SOURCES CONFIGURE_DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/Test*.cpp)
add_executable(IronSimTests ${IRON_TEST_SOURCES})
target_link_libraries(IronSimTests PRIVATE IronSimCore)
target_include_directories(IronSimTests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
target_compile_options(IronSimTests PRIVATE -Wall -Wextra -Wshadow -Werror)
target_compile_definitions(IronSimTests PRIVATE IRON_DATA_DIR="${CMAKE_CURRENT_SOURCE_DIR}/../Content/Data")

enable_testing()
add_test(NAME IronSimTests COMMAND IronSimTests)
