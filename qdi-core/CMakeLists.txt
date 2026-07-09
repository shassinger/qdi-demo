cmake_minimum_required(VERSION 3.20)
project(qdi-core LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include_directories(include)

add_library(qdi_mock SHARED src/qdi_mock.cpp)

set_target_properties(qdi_mock PROPERTIES
    PREFIX ""
    SUFFIX ".so"
)

if(APPLE)
    set_target_properties(qdi_mock PROPERTIES
        SUFFIX ".dylib"
    )
endif()
