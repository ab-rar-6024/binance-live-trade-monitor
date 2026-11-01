package binance.hadoop;

import java.io.File;
import java.io.FileNotFoundException;
import java.io.IOException;

import org.apache.hadoop.fs.FileStatus;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.fs.RawLocalFileSystem;
import org.apache.hadoop.fs.permission.FsPermission;

/**
 * A local file system for Hadoop/Spark on Windows that needs neither winutils.exe nor hadoop.dll.
 *
 * Spark Structured Streaming writes checkpoints and state through the Hadoop FileSystem API.
 * On Windows, Hadoop's RawLocalFileSystem
 *   - runs "winutils.exe chmod ..." for every file it creates, and
 *   - calls a native access() check (hadoop.dll) when listing a directory.
 * Both binaries are separate, third-party builds that are not part of Spark or Hadoop.
 * File permissions are meaningless for local checkpoints, so the permission calls become
 * no-ops and directory listing uses plain java.io. Everything else (create, rename,
 * delete, status) is inherited unchanged.
 */
public class WinSafeFileSystem extends RawLocalFileSystem {

    @Override
    public void setPermission(Path p, FsPermission permission) throws IOException {
        // intentionally empty: no winutils on Windows
    }

    @Override
    public void setOwner(Path p, String username, String groupname) throws IOException {
        // intentionally empty
    }

    @Override
    public FileStatus[] listStatus(Path f) throws IOException {
        File local = pathToFile(f);
        if (!local.exists()) {
            throw new FileNotFoundException("File " + f + " does not exist");
        }
        if (local.isFile()) {
            return new FileStatus[] {getFileStatus(f)};
        }
        String[] names = local.list();
        if (names == null) {
            return new FileStatus[0];
        }
        FileStatus[] result = new FileStatus[names.length];
        for (int i = 0; i < names.length; i++) {
            result[i] = getFileStatus(new Path(f, names[i]));
        }
        return result;
    }
}
