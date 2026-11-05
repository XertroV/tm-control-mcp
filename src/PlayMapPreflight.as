namespace TmMcp {
    Json::Value PlayMapPreflight(const string &in path) {
        auto result = Json::Object();
        result["coverage"] = "envelope-only";
        result["embeddedContentVerified"] = false;
        result["state"] = "unresolved";
        result["warning"] = "Embedded map items are not validated. A plausible GBX envelope does not prevent native loader crashes; only load trusted content.";
        if (path.Contains("://")) { result["state"] = "remote_uninspected"; return result; }
        string resolved = path;
        if (!IO::FileExists(resolved)) {
            string relative = FidsNormPath(path);
            if (!relative.ToLower().StartsWith("maps/")) relative = "Maps/" + relative;
            resolved = IO::FromUserGameFolder(relative);
            auto fid = Fids::GetUser(relative);
            if (fid !is null && fid.OSCheckIfExists() && string(fid.FullFileName) != "<virtual>") {
                resolved = string(fid.FullFileName);
            }
        }
        if (!IO::FileExists(resolved)) return result; // Engine paths may be virtual.
        try {
            IO::File f(resolved, IO::FileMode::Read);
            uint64 size = f.Size();
            string bytes = "";
            if (size >= 21) bytes = f.Read(21).ReadString(21);
            else if (size > 0) bytes = f.Read(size).ReadString(size);
            f.Close();
            result["fileBytes"] = int64(size);
            result["state"] = PlayMapEnvelopeState(bytes, size);
        } catch {
            result["state"] = "unreadable";
            result["reason"] = getExceptionInfo();
        }
        return result;
    }
}
