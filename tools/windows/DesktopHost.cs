using System;
using System.ComponentModel;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;

[assembly: AssemblyTitle("DBA工作台")]
[assembly: AssemblyProduct("DBA工作台")]

internal static class DesktopHost
{
    private const uint LoadLibrarySearchDllLoadDir = 0x00000100;
    private const uint LoadLibrarySearchDefaultDirs = 0x00001000;

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    private static extern IntPtr LoadLibraryEx(string path, IntPtr reserved, uint flags);

    [DllImport("kernel32.dll", CharSet = CharSet.Ansi, ExactSpelling = true, SetLastError = true)]
    private static extern IntPtr GetProcAddress(IntPtr library, string export);

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    private delegate int PythonMain(int argc, IntPtr argv);

    [STAThread]
    private static int Main(string[] args)
    {
        if (args.Length < 3 || !File.Exists(args[0]))
        {
            Console.Error.WriteLine("DBA 工作台启动失败，未找到指定的 Python 运行库。");
            return 1;
        }

        var runtime = LoadLibraryEx(Path.GetFullPath(args[0]), IntPtr.Zero,
            LoadLibrarySearchDllLoadDir | LoadLibrarySearchDefaultDirs);
        var entry = runtime == IntPtr.Zero ? IntPtr.Zero : GetProcAddress(runtime, "Py_Main");
        if (entry == IntPtr.Zero)
        {
            Console.Error.WriteLine(new Win32Exception(Marshal.GetLastWin32Error()).Message);
            return 1;
        }

        // Use the venv interpreter path as argv[0] so Python loads that venv.
        var arguments = new IntPtr[args.Length - 1];
        var argv = Marshal.AllocHGlobal((arguments.Length + 1) * IntPtr.Size);
        try
        {
            for (var i = 0; i < arguments.Length; i++)
            {
                arguments[i] = Marshal.StringToHGlobalUni(args[i + 1]);
                Marshal.WriteIntPtr(argv, i * IntPtr.Size, arguments[i]);
            }
            Marshal.WriteIntPtr(argv, arguments.Length * IntPtr.Size, IntPtr.Zero);
            var run = (PythonMain)Marshal.GetDelegateForFunctionPointer(entry, typeof(PythonMain));
            return run(arguments.Length, argv);
        }
        finally
        {
            foreach (var argument in arguments)
                Marshal.FreeHGlobal(argument);
            Marshal.FreeHGlobal(argv);
        }
    }
}
