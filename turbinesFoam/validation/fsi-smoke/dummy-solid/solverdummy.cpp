/*
  Mock structural participant for the of-plugins ASM FSI smoke test.

  It mirrors the official preCICE C++ solverdummy (venv/share/precice/
  examples/solverdummies/cpp) but supports an arbitrary number of interface
  meshes (one per blade) and reads its vertices from coordinates files:

    - each mesh provides <name> (the participant's own mesh) and reads the
      aerodynamic Force on it;
    - it returns a mock Displacement following a simple linear spring law
      u = k * F (clamped), enough to exercise the coupling and observe the
      behaviour.

  Meshes file format (one entry per line, '#' starts a comment):

      <meshName> <coordinates.dat>

  Usage:
    solverdummy <precice-config.xml> <participant> <meshesFile> [traceFile]

  The optional traceFile receives, per time window and per point, the
  received force and the written displacement (the correctness checker
  compares it against the fluid-side trace).
*/

#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "precice/precice.hpp"

namespace
{

struct MeshInterface
{
    std::string name;
    int n = 0;
    std::vector<int> vertexIDs;
    std::vector<double> force;  // read
    std::vector<double> disp;   // written
};

std::vector<double> readCoordinates(const std::string& fileName)
{
    std::ifstream f(fileName);
    if (!f)
    {
        throw std::runtime_error(
            "cannot open coordinates file \"" + fileName + "\"");
    }

    std::vector<double> coords;
    std::string line;
    while (std::getline(f, line))
    {
        if (line.empty() || line[0] == '#')
        {
            continue;
        }
        std::istringstream ss(line);
        double x, y, z;
        if (ss >> x >> y >> z)
        {
            coords.push_back(x);
            coords.push_back(y);
            coords.push_back(z);
        }
    }
    return coords;
}

}  // namespace

int main(int argc, char** argv)
{
    if (argc != 4 && argc != 5)
    {
        std::cout
            << "Usage: solverdummy <precice-config.xml> <participant> "
               "<meshesFile> [traceFile]\n";
        return EXIT_FAILURE;
    }

    const std::string configFileName(argv[1]);
    const std::string solverName(argv[2]);
    const std::string meshesFileName(argv[3]);
    const std::string traceFileName = (argc == 5) ? argv[4] : "";

    if (!traceFileName.empty())
    {
        // Truncate any previous trace
        std::ofstream trace(traceFileName, std::ios::trunc);
        trace << "# step mesh point Fx Fy Fz ux uy uz\n";
    }

    // Fixed interface contract for this harness
    const std::string readDataName = "Force";
    const std::string writeDataName = "Displacement";
    const int dimensions = 3;

    // Mock spring stiffness [m/N] and a safety clamp on |u| [m]
    const double kSpring = 1.0e-6;
    const double uMax = 1.0e-2;

    std::cout << "DUMMY: participant \"" << solverName << "\" reading \""
              << readDataName << "\", writing \"" << writeDataName << "\"\n";

    // ---- Interface meshes --------------------------------------------------
    std::vector<MeshInterface> meshes;

    {
        std::ifstream f(meshesFileName);
        if (!f)
        {
            std::cerr << "DUMMY: cannot open meshes file \"" << meshesFileName
                      << "\"\n";
            return EXIT_FAILURE;
        }

        std::string line;
        while (std::getline(f, line))
        {
            if (line.empty() || line[0] == '#')
            {
                continue;
            }
            std::istringstream ss(line);
            std::string name, coordsFile;
            if (!(ss >> name >> coordsFile))
            {
                continue;
            }

            MeshInterface m;
            m.name = name;
            const std::vector<double> coords = readCoordinates(coordsFile);
            if (coords.empty() || coords.size() % dimensions != 0)
            {
                std::cerr << "DUMMY: bad coordinates for mesh \"" << name
                          << "\"\n";
                return EXIT_FAILURE;
            }
            m.n = static_cast<int>(coords.size()) / dimensions;
            m.vertexIDs.resize(m.n);
            m.force.assign(coords.size(), 0.0);
            m.disp.assign(coords.size(), 0.0);

            std::cout << "DUMMY: mesh \"" << m.name << "\" (" << m.n
                      << " vertices)\n";

            meshes.push_back(std::move(m));

            // Keep the coordinates around for setMeshVertices
            // (re-read is cheap and keeps the struct small)
        }
    }

    if (meshes.empty())
    {
        std::cerr << "DUMMY: no meshes\n";
        return EXIT_FAILURE;
    }

    precice::Participant participant(solverName, configFileName, 0, 1);

    // Register vertices (re-read the coordinates to avoid storing them twice)
    {
        std::ifstream f(meshesFileName);
        std::string line;
        std::size_t idx = 0;
        while (std::getline(f, line))
        {
            if (line.empty() || line[0] == '#')
            {
                continue;
            }
            std::istringstream ss(line);
            std::string name, coordsFile;
            if (!(ss >> name >> coordsFile))
            {
                continue;
            }
            const std::vector<double> coords = readCoordinates(coordsFile);
            participant.setMeshVertices(
                meshes[idx].name, coords, meshes[idx].vertexIDs);
            idx++;
        }
    }

    if (participant.requiresInitialData())
    {
        std::cout << "DUMMY: writing initial data\n";
        for (auto& m : meshes)
        {
            participant.writeData(m.name, writeDataName, m.vertexIDs, m.disp);
        }
    }

    participant.initialize();

    int step = 0;
    while (participant.isCouplingOngoing())
    {
        if (participant.requiresWritingCheckpoint())
        {
            std::cout << "DUMMY: writing checkpoint\n";
        }

        const double dt = participant.getMaxTimeStepSize();

        double maxU = 0.0;

        for (auto& m : meshes)
        {
            participant.readData(
                m.name, readDataName, m.vertexIDs, dt, m.force);

            for (int i = 0; i < m.n; i++)
            {
                for (int d = 0; d < dimensions; d++)
                {
                    double u = kSpring * m.force.at(dimensions * i + d);
                    u = std::max(-uMax, std::min(uMax, u));
                    m.disp.at(dimensions * i + d) = u;
                    maxU = std::max(maxU, std::abs(u));
                }
            }
        }

        for (auto& m : meshes)
        {
            participant.writeData(
                m.name, writeDataName, m.vertexIDs, m.disp);
        }

        if (!traceFileName.empty())
        {
            std::ofstream trace(traceFileName, std::ios::app);
            for (const auto& m : meshes)
            {
                for (int i = 0; i < m.n; i++)
                {
                    trace << step << ' ' << m.name << ' ' << i;
                    for (int d = 0; d < dimensions; d++)
                        trace << ' ' << m.force.at(dimensions * i + d);
                    for (int d = 0; d < dimensions; d++)
                        trace << ' ' << m.disp.at(dimensions * i + d);
                    trace << '\n';
                }
            }
        }

        if (step % 10 == 0)
        {
            std::cout << "DUMMY: step " << step << " max|u| = " << maxU
                      << " m\n";
        }

        participant.advance(dt);

        if (participant.requiresReadingCheckpoint())
        {
            std::cout << "DUMMY: reading checkpoint\n";
        }

        step++;
    }

    participant.finalize();

    std::cout << "DUMMY: closing after " << step << " steps\n";

    return 0;
}
