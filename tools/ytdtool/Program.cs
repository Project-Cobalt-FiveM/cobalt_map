using CodeWalker.GameFiles;
using CodeWalker.Utils;
using System.Globalization;
using SharpDX;

CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;

return args.Length == 0 ? Usage() : args[0] switch
{
    "find" when args.Length == 3 => Find(args[1], args[2]),
    "extract" when args.Length >= 4 => Extract(args[1], args[2], args[3..]),
    "pack" when args.Length == 3 => Pack(args[1], args[2]),
    "mesh" when args.Length == 3 => Mesh(args[1], args[2]),
    "recolour" when args.Length == 6 => Recolour(args[1], args[2], args[3], args[4], args[5]),
    "info" when args.Length >= 2 => Info(args[1..]),
    "unpack" when args.Length == 3 => Unpack(args[1], args[2]),
    "raw" when args.Length >= 4 => Raw(args[1], args[2], args[3..]),
    "xml" when args.Length == 3 => Xml(args[1], args[2]),
    "yddxml" when args.Length == 3 => YddXmlDump(args[1], args[2]),
    "layers" when args.Length == 3 => Layers(args[1], args[2]),
    _ => Usage(),
};

static Dictionary<string, RpfFileEntry> LatestEntries(string gtaDir, IEnumerable<string> names)
{
    var wanted = names.Select(n => n.ToLowerInvariant()).ToHashSet();
    var latest = new Dictionary<string, RpfFileEntry>();
    foreach (var entry in Entries(OpenGame(gtaDir)).Where(e => wanted.Contains(e.NameLower)))
    {
        latest[entry.NameLower] = entry;
    }
    wanted.Except(latest.Keys).ToList().ForEach(n => Console.Error.WriteLine($"not found: {n}"));
    return latest;
}

static int Xml(string gtaDir, string name)
{
    var (_, entry) = LatestEntries(gtaDir, [name]).Single();
    Console.WriteLine(MetaXml.GetXml(entry, entry.File.ExtractFile(entry), out _));
    return 0;
}

static int Layers(string gtaDir, string name)
{
    var (_, entry) = LatestEntries(gtaDir, [name]).Single();
    var ydd = new YddFile();
    ydd.Load(entry.File.ExtractFile(entry), entry);
    var hashes = ydd.DrawableDict.Hashes ?? [];
    for (var i = 0; i < ydd.Drawables.Length; i++)
    {
        var drawable = ydd.Drawables[i];
        var geometries = (drawable.AllModels ?? []).SelectMany(m => m.Geometries ?? []).ToList();
        var stats = geometries.Select(g =>
        {
            var v = g.VertexData;
            var zs = Enumerable.Range(0, v.VertexCount).Select(k => v.GetVector3(k, 0).Z).ToList();
            var colours = Enumerable.Range(0, v.VertexCount).Select(k => VertexColour(v, k).ToString("X8")).Distinct();
            return $"z {zs.Min()}..{zs.Max()} v{v.VertexCount} [{string.Join(",", colours)}]";
        });
        var hash = i < hashes.Length ? hashes[i].ToString("X8") : "?";
        Console.WriteLine($"{i}\t{hash}\t{drawable.BoundingBoxMin.X:F0},{drawable.BoundingBoxMin.Y:F0}..{drawable.BoundingBoxMax.X:F0},{drawable.BoundingBoxMax.Y:F0}\t{string.Join(" | ", stats)}");
    }
    return 0;
}

static int YddXmlDump(string source, string name)
{
    var ydd = new YddFile();
    if (File.Exists(Path.Combine(source, name)))
    {
        ydd.Load(File.ReadAllBytes(Path.Combine(source, name)));
    }
    else
    {
        var (_, entry) = LatestEntries(source, [name]).Single();
        ydd.Load(entry.File.ExtractFile(entry), entry);
    }
    Console.WriteLine(YddXml.GetXml(ydd));
    return 0;
}

static int Raw(string gtaDir, string outDir, string[] names)
{
    var latest = LatestEntries(gtaDir, names);
    Directory.CreateDirectory(outDir);
    foreach (var (name, entry) in latest)
    {
        File.WriteAllBytes(Path.Combine(outDir, name), entry.File.ExtractFile(entry));
        Console.WriteLine(entry.Path);
    }
    return latest.Count == names.Length ? 0 : 1;
}

static int Unpack(string file, string outDir)
{
    var ytd = new YtdFile();
    ytd.Load(File.ReadAllBytes(file));
    Directory.CreateDirectory(outDir);
    foreach (var texture in ytd.TextureDict.Textures.data_items)
    {
        File.WriteAllBytes(Path.Combine(outDir, texture.Name + ".dds"), DDSIO.GetDDSFile(texture));
    }
    return 0;
}

static int Info(string[] files)
{
    foreach (var file in files.Where(f => f.EndsWith(".ydd", StringComparison.OrdinalIgnoreCase)))
    {
        var ydd = new YddFile();
        ydd.Load(File.ReadAllBytes(file));
        var colours = Geometries(ydd)
            .SelectMany(g => Enumerable.Range(0, g.VertexData.VertexCount).Select(i => VertexColour(g.VertexData, i)))
            .Distinct()
            .Select(c => c.ToString("X8"));
        Console.WriteLine($"{Path.GetFileName(file)}\t{ydd.Drawables.Length} drawables\t{string.Join(",", colours)}");
    }

    foreach (var file in files.Where(f => f.EndsWith(".ytd", StringComparison.OrdinalIgnoreCase)))
    {
        var ytd = new YtdFile();
        ytd.Load(File.ReadAllBytes(file));
        foreach (var texture in ytd.TextureDict.Textures.data_items)
        {
            Console.WriteLine($"{Path.GetFileName(file)}\t{texture.Name}\t{texture.Width}x{texture.Height}\t{texture.Format}\t{texture.Levels}");
        }
    }
    return 0;
}

static IEnumerable<(RpfFileEntry Entry, YddFile Ydd)> MinimapDrawables(string gtaDir)
{
    foreach (var entry in Entries(OpenGame(gtaDir)).Where(e => e.NameLower.StartsWith("minimap_") && e.NameLower.EndsWith(".ydd")))
    {
        var ydd = new YddFile();
        ydd.Load(entry.File.ExtractFile(entry), entry);
        yield return (entry, ydd);
    }
}

static IEnumerable<DrawableGeometry> Geometries(YddFile ydd) =>
    ydd.Drawables
        .SelectMany(d => d.AllModels ?? [])
        .SelectMany(m => m.Geometries ?? [])
        .Where(g => g.VertexData != null && g.IndexBuffer?.Indices != null);

static uint VertexColour(VertexData vertices, int index) =>
    BitConverter.ToUInt32(vertices.VertexBytes, index * vertices.VertexStride + 12);

static IEnumerable<YddFile> StreamedDrawables(string dir) =>
    Directory.GetFiles(dir, "minimap_*.ydd").Select(file =>
    {
        var ydd = new YddFile();
        ydd.Load(File.ReadAllBytes(file));
        return ydd;
    });

static int Mesh(string source, string outFile)
{
    var ydds = File.Exists(Path.Combine(source, "GTA5.exe"))
        ? MinimapDrawables(source).Select(d => d.Ydd)
        : StreamedDrawables(source);
    using var writer = new StreamWriter(outFile);
    foreach (var geometry in ydds.SelectMany(Geometries))
    {
        var vertices = geometry.VertexData;
        var indices = geometry.IndexBuffer.Indices;
        for (var i = 0; i + 2 < indices.Length; i += 3)
        {
            var corners = new[] { indices[i], indices[i + 1], indices[i + 2] }.Select(v => vertices.GetVector3(v, 0)).ToList();
            var points = string.Join("\t", corners.Select(p => $"{p.X:F2}\t{p.Y:F2}"));
            writer.WriteLine($"{VertexColour(vertices, indices[i]):X8}\t{points}\t{corners.Average(p => p.Z):F2}");
        }
    }
    return 0;
}

static string CellName(Vector2 point) =>
    $"minimap_{(int)Math.Floor((point.X + 4500f) / 1175f)}_{(int)Math.Floor((8000f - point.Y) / 1388f)}.ydd";

static Dictionary<string, List<OverlayLabel>> LoadOverlay(string overlayFile)
{
    var labels = File.ReadLines(overlayFile)
        .Select(line => line.Split('\t'))
        .GroupBy(cols => cols[0])
        .Select(group => new OverlayLabel(group.Select(cols =>
        {
            var values = cols.Skip(2).Select(v => float.Parse(v, CultureInfo.InvariantCulture)).ToArray();
            var corners = new[] { new Vector2(values[1], values[2]), new Vector2(values[3], values[4]), new Vector2(values[5], values[6]) };
            return new OverlayTriangle(Convert.ToUInt32(cols[1], 16), values[0], corners);
        }).ToList()));
    return labels.GroupBy(label => CellName(label.Centre)).ToDictionary(g => g.Key, g => g.ToList());
}

static float AverageZ(DrawableGeometry geometry) =>
    Enumerable.Range(0, Math.Min(geometry.VertexData.VertexCount, 16)).Average(i => geometry.VertexData.GetVector3(i, 0).Z);

static bool IsDetail(DrawableBase drawable) => drawable.BoundingBoxMin.Z >= DetailMinZ;

static DrawableBase TargetDrawable(YddFile ydd, Vector2 centre)
{
    var candidates = ydd.Drawables.Where(IsDetail).DefaultIfEmpty(ydd.Drawables.MaxBy(d => d.BoundingBoxMax.Z)!).ToList();
    return candidates.FirstOrDefault(d =>
        centre.X >= d.BoundingBoxMin.X && centre.X <= d.BoundingBoxMax.X &&
        centre.Y >= d.BoundingBoxMin.Y && centre.Y <= d.BoundingBoxMax.Y)
        ?? candidates.MinBy(d => Vector2.Distance(centre, new Vector2(d.BoundingCenter.X, d.BoundingCenter.Y)))!;
}

static List<RectangleF> LoadKnockouts(string file) =>
    File.ReadLines(file)
        .Select(line => line.Split('\t').Select(v => float.Parse(v, CultureInfo.InvariantCulture)).ToArray())
        .Select(v => new RectangleF(v[0], v[1], v[2] - v[0], v[3] - v[1]))
        .ToList();

static bool Overlaps(RectangleF rect, IList<Vector3> polygon) =>
    polygon.Max(p => p.X) > rect.Left && polygon.Min(p => p.X) < rect.Right &&
    polygon.Max(p => p.Y) > rect.Top && polygon.Min(p => p.Y) < rect.Bottom;

static List<Vector3> ClipHalfPlane(List<Vector3> polygon, Func<Vector3, float> inside)
{
    var result = new List<Vector3>();
    for (var i = 0; i < polygon.Count; i++)
    {
        var current = polygon[i];
        var previous = polygon[(i + polygon.Count - 1) % polygon.Count];
        float dc = inside(current), dp = inside(previous);
        if ((dc >= 0) != (dp >= 0))
        {
            result.Add(Vector3.Lerp(previous, current, dp / (dp - dc)));
        }
        if (dc >= 0)
        {
            result.Add(current);
        }
    }
    return result;
}

static IEnumerable<List<Vector3>> Subtract(List<Vector3> polygon, RectangleF rect)
{
    if (!Overlaps(rect, polygon))
    {
        yield return polygon;
        yield break;
    }
    yield return ClipHalfPlane(polygon, p => rect.Left - p.X);
    yield return ClipHalfPlane(polygon, p => p.X - rect.Right);
    var middle = ClipHalfPlane(ClipHalfPlane(polygon, p => p.X - rect.Left), p => rect.Right - p.X);
    yield return ClipHalfPlane(middle, p => rect.Top - p.Y);
    yield return ClipHalfPlane(middle, p => p.Y - rect.Bottom);
}

static int CutKnockouts(DrawableGeometry geometry, List<RectangleF> knockouts)
{
    var vertices = geometry.VertexData;
    var indices = geometry.IndexBuffer.Indices;
    var positions = Enumerable.Range(0, vertices.VertexCount).Select(i => vertices.GetVector3(i, 0)).ToList();
    var local = knockouts.Where(r => Overlaps(r, positions)).ToList();
    if (local.Count == 0) return 0;

    var output = new List<Corner>();
    var cut = 0;
    for (var i = 0; i + 2 < indices.Length; i += 3)
    {
        var corners = new List<Vector3> { positions[indices[i]], positions[indices[i + 1]], positions[indices[i + 2]] };
        var hits = corners.Average(c => c.Z) >= DetailMinZ ? local.Where(r => Overlaps(r, corners)).ToList() : [];
        if (hits.Count == 0)
        {
            output.AddRange(Enumerable.Range(0, 3).Select(k => new Corner(corners[k], VertexColour(vertices, indices[i + k]))));
            continue;
        }

        cut++;
        var colour = VertexColour(vertices, indices[i]);
        var pieces = hits.Aggregate(new List<List<Vector3>> { corners }, (acc, rect) => acc.SelectMany(p => Subtract(p, rect)).Where(p => p.Count >= 3).ToList());
        foreach (var piece in pieces)
        {
            for (var k = 1; k + 1 < piece.Count; k++)
            {
                output.Add(new Corner(piece[0], colour));
                output.Add(new Corner(piece[k], colour));
                output.Add(new Corner(piece[k + 1], colour));
            }
        }
    }

    if (cut == 0) return 0;

    var (unique, slots) = Deduplicate(output);
    if (unique.Count > ushort.MaxValue) throw new InvalidOperationException("knockouts push a geometry past 65535 vertices");
    vertices.VertexBytes = VertexBytes(unique);
    vertices.VertexCount = unique.Count;
    geometry.IndexBuffer.Indices = slots.Select(slot => (ushort)slot).ToArray();
    geometry.IndexBuffer.IndicesCount = (uint)slots.Count;
    return cut;
}

static (List<Corner> Unique, List<int> Slots) Deduplicate(IEnumerable<Corner> corners)
{
    var unique = new List<Corner>();
    var slotOf = new Dictionary<Corner, int>();
    var slots = new List<int>();
    foreach (var corner in corners)
    {
        if (!slotOf.TryGetValue(corner, out var slot))
        {
            slot = unique.Count;
            slotOf[corner] = slot;
            unique.Add(corner);
        }
        slots.Add(slot);
    }
    return (unique, slots);
}

static byte[] VertexBytes(List<Corner> corners)
{
    var bytes = new byte[corners.Count * 16];
    for (var v = 0; v < corners.Count; v++)
    {
        BitConverter.TryWriteBytes(bytes.AsSpan(v * 16, 4), corners[v].Position.X);
        BitConverter.TryWriteBytes(bytes.AsSpan(v * 16 + 4, 4), corners[v].Position.Y);
        BitConverter.TryWriteBytes(bytes.AsSpan(v * 16 + 8, 4), corners[v].Position.Z);
        BitConverter.TryWriteBytes(bytes.AsSpan(v * 16 + 12, 4), corners[v].Colour);
    }
    return bytes;
}

static bool AppendLabel(YddFile ydd, OverlayLabel label)
{
    var drawable = TargetDrawable(ydd, label.Centre);
    var (unique, slots) = Deduplicate(label.Triangles.SelectMany(t =>
        t.Corners.Select(c => new Corner(new Vector3(c.X, c.Y, t.Z), t.Colour))));
    var geometry = (drawable.AllModels ?? [])
        .SelectMany(m => m.Geometries ?? [])
        .Where(g => g.VertexData != null && g.IndexBuffer?.Indices != null && g.VertexData.VertexStride == 16)
        .Where(g => g.VertexData.VertexCount + unique.Count <= ushort.MaxValue)
        .OrderByDescending(AverageZ)
        .FirstOrDefault();
    if (geometry == null) return false;

    var vertices = geometry.VertexData;
    var first = vertices.VertexCount;
    var bytes = new byte[(first + unique.Count) * 16];
    Buffer.BlockCopy(vertices.VertexBytes, 0, bytes, 0, first * 16);
    VertexBytes(unique).CopyTo(bytes, first * 16);
    vertices.VertexBytes = bytes;
    vertices.VertexCount = first + unique.Count;

    var indices = geometry.IndexBuffer;
    indices.Indices = indices.Indices.Concat(slots.Select(slot => (ushort)(first + slot))).ToArray();
    indices.IndicesCount = (uint)indices.Indices.Length;

    var corners = label.Triangles.SelectMany(t => t.Corners).ToList();
    drawable.BoundingBoxMin = Vector3.Min(drawable.BoundingBoxMin, new Vector3(corners.Min(c => c.X), corners.Min(c => c.Y), drawable.BoundingBoxMin.Z));
    drawable.BoundingBoxMax = Vector3.Max(drawable.BoundingBoxMax, new Vector3(corners.Max(c => c.X), corners.Max(c => c.Y), 16f));
    return true;
}

static int Recolour(string gtaDir, string mappingFile, string overlayFile, string knockoutFile, string outDir)
{
    var knockouts = LoadKnockouts(knockoutFile);
    var cutTriangles = 0;
    var mapping = File.ReadLines(mappingFile)
        .Select(line => line.Split('\t'))
        .ToDictionary(cols => Convert.ToUInt32(cols[0], 16), cols => Convert.ToUInt32(cols[1], 16));
    var overlay = LoadOverlay(overlayFile);
    var appended = 0;
    var failed = 0;
    Directory.CreateDirectory(outDir);

    foreach (var (entry, ydd) in MinimapDrawables(gtaDir))
    {
        foreach (var vertices in Geometries(ydd).Select(g => g.VertexData))
        {
            for (var i = 0; i < vertices.VertexCount; i++)
            {
                if (!mapping.TryGetValue(VertexColour(vertices, i), out var colour)) continue;
                BitConverter.TryWriteBytes(vertices.VertexBytes.AsSpan(i * vertices.VertexStride + 12, 4), colour);
            }
        }
        foreach (var geometry in Geometries(ydd).Where(g => g.VertexData.VertexStride == 16))
        {
            cutTriangles += CutKnockouts(geometry, knockouts);
        }
        if (overlay.Remove(entry.NameLower, out var labels))
        {
            var added = labels.Count(label => AppendLabel(ydd, label));
            appended += added;
            failed += labels.Count - added;
        }
        File.WriteAllBytes(Path.Combine(outDir, entry.Name), ydd.Save());
    }

    var dropped = overlay.Values.Sum(labels => labels.Count);
    Console.WriteLine($"{appended} overlay labels added, {failed} with no room in their drawable, {dropped} outside the radar's cells, {cutTriangles} road and building triangles cut under labels");
    return failed > 0 ? 1 : 0;
}

static int Usage()
{
    Console.Error.WriteLine("ytdtool find <gtaDir> <nameFragment>");
    Console.Error.WriteLine("ytdtool extract <gtaDir> <outDir> <ytdName>...");
    Console.Error.WriteLine("ytdtool pack <ddsDir> <outYtd>");
    Console.Error.WriteLine("ytdtool mesh <gtaDir or streamDir> <outTsv>");
    Console.Error.WriteLine("ytdtool recolour <gtaDir> <coloursTsv> <overlayTsv> <knockoutsTsv> <outDir>");
    Console.Error.WriteLine("ytdtool info <file.ytd|file.ydd>...");
    Console.Error.WriteLine("ytdtool unpack <file.ytd> <outDir>");
    Console.Error.WriteLine("ytdtool raw <gtaDir> <outDir> <name>...");
    Console.Error.WriteLine("ytdtool xml <gtaDir> <name.ymt>");
    Console.Error.WriteLine("ytdtool yddxml <gtaDir or folder> <name.ydd>");
    Console.Error.WriteLine("ytdtool layers <gtaDir> <name.ydd>");
    return 2;
}

static RpfManager OpenGame(string gtaDir)
{
    GTA5Keys.LoadFromPath(gtaDir, false, null);
    var manager = new RpfManager { EnableMods = false };
    manager.Init(gtaDir, false, _ => { }, Console.Error.WriteLine);
    return manager;
}

static IEnumerable<RpfFileEntry> Entries(RpfManager manager) =>
    manager.AllRpfs
        .Where(rpf => !rpf.Path.StartsWith("mods", StringComparison.OrdinalIgnoreCase))
        .SelectMany(rpf => rpf.AllEntries)
        .OfType<RpfFileEntry>();

static int Find(string gtaDir, string fragment)
{
    foreach (var entry in Entries(OpenGame(gtaDir)).Where(e => e.NameLower.Contains(fragment.ToLowerInvariant())))
    {
        Console.WriteLine($"{entry.Path}\t{entry.FileSize}");
    }
    return 0;
}

static int Extract(string gtaDir, string outDir, string[] names)
{
    var latest = LatestEntries(gtaDir, names);
    foreach (var (name, entry) in latest)
    {
        var data = entry.File.ExtractFile(entry);
        var ytdDir = Path.Combine(outDir, Path.GetFileNameWithoutExtension(name));
        Directory.CreateDirectory(ytdDir);

        var ytd = new YtdFile();
        ytd.Load(data, entry);
        foreach (var texture in ytd.TextureDict.Textures.data_items)
        {
            File.WriteAllBytes(Path.Combine(ytdDir, texture.Name + ".dds"), DDSIO.GetDDSFile(texture));
            Console.WriteLine($"{entry.Path}\t{texture.Name}\t{texture.Width}x{texture.Height}\t{texture.Format}\t{texture.Levels}");
        }
    }

    return latest.Count == names.Length ? 0 : 1;
}

static int Pack(string ddsDir, string outYtd)
{
    var textures = Directory.GetFiles(ddsDir, "*.dds").Order().Select(path =>
    {
        var name = Path.GetFileNameWithoutExtension(path);
        var texture = DDSIO.GetTexture(File.ReadAllBytes(path));
        texture.Name = name;
        texture.NameHash = JenkHash.GenHash(name.ToLowerInvariant());
        return texture;
    }).ToList();

    var ytd = new YtdFile { TextureDict = new TextureDictionary() };
    ytd.TextureDict.BuildFromTextureList(textures);
    Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(outYtd))!);
    File.WriteAllBytes(outYtd, ytd.Save());
    Console.WriteLine($"{outYtd}\t{textures.Count} textures");
    return 0;
}

static partial class Program
{
    const float DetailMinZ = 3f;
}

record OverlayTriangle(uint Colour, float Z, Vector2[] Corners);

readonly record struct Corner(Vector3 Position, uint Colour);

record OverlayLabel(List<OverlayTriangle> Triangles)
{
    public Vector2 Centre { get; } = Triangles.SelectMany(t => t.Corners).Aggregate(Vector2.Zero, (a, b) => a + b)
        / (Triangles.Count * 3);
}
