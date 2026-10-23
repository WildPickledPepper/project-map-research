#pragma once
// Experimental capture helper, copied only into the isolated P5 product checkout.
#include <sstream>
#include <thread>
#include <typeinfo>
#include "ProtocolUtil.h"
#include "ServerLog.h"
#include "stringbuffer.h"
#include "writer.h"

namespace ProjectMapProbe {
struct Identity {
    unsigned int requestId;
    std::string module;
    std::string command;
    std::string project;
};
inline Identity Capture(const Dic::Protocol::Request &request) {
    return {request.id, request.moduleName, request.command, request.projectName};
}
inline void Emit(const char *stage, const Identity &request, const char *implementation = "",
                 int count = -1, const char *traceId = "") {
    rapidjson::StringBuffer buffer;
    rapidjson::Writer<rapidjson::StringBuffer> writer(buffer);
    std::ostringstream thread;
    thread << std::this_thread::get_id();
    writer.StartObject();
    writer.Key("stage"); writer.String(stage);
    writer.Key("request_id"); writer.Uint(request.requestId);
    writer.Key("module"); writer.String(request.module.c_str());
    writer.Key("command"); writer.String(request.command.c_str());
    writer.Key("project"); writer.String(request.project.c_str());
    writer.Key("implementation"); writer.String(implementation);
    writer.Key("thread"); writer.String(thread.str().c_str());
    writer.Key("count"); writer.Int(count);
    writer.Key("trace_id"); writer.String(traceId);
    writer.EndObject();
    Dic::Server::ServerLog::Info("PROJECT_MAP_EVENT ", buffer.GetString());
}
inline std::string TraceId(const Dic::document_t &document) {
    if (!document.IsObject() || !document.HasMember("params") || !document["params"].IsObject()) return "";
    const auto &params = document["params"];
    if (!params.HasMember("__projectMapTrace") || !params["__projectMapTrace"].IsString()) return "";
    return params["__projectMapTrace"].GetString();
}
}
