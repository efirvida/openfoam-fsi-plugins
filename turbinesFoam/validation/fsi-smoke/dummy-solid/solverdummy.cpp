/*
  Mock structural participant for the of-plugins ASM FSI smoke test.

  It mirrors the official preCICE C++ solverdummy (venv/share/precice/
  examples/solverdummies/cpp) but:

    - reads its interface vertices from a coordinates file (one "x y z" per
      line) instead of the hardcoded three points, so the fluid and the solid
      share the same point cloud;
    - reads the aerodynamic Force and returns a mock Displacement following a
      simple linear spring law  u = k * F  (clamped), which is enough to
      exercise the coupling and observe the behaviour.

  Usage:
    solverdummy <precice-config.xml> <participant> <coordinates.dat>
*/

#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

#include "precice/precice.hpp"

int main(int argc, char** argv)
{
    if (argc != 4)
    {
        std::cout
            << "Usage: solverdummy <precice-config.xml> <participant> "
               "<coordinates.dat>\n";
        return EXIT_FAILURE;
    }

    const std::string configFileName(argv[1]);
    const std::string solverName(argv[2]);
    const std::string coordsFileName(argv[3]);

    // Fixed interface contract for this harness
    const std::string meshName = solverName + "-Mesh";
    const std::string readDataName = "Force";
    const std::string writeDataName = "Displacement";

    // Mock spring stiffness [m/N] and a safety clamp on |u| [m]
    const double kSpring = 1.0e-6;
    const double uMax = 1.0e-2;

    std::cout << "DUMMY: participant \"" << solverName
              << "\" (" << meshName << ") reading \"" << readDataName
              << "\", writing \"" << writeDataName << "\"\n";

    // ---- Interface vertices ------------------------------------------------
    std::ifstream coordsFile(coordsFileName);
    if (!coordsFile)
    {
        std::cerr << "DUMMY: cannot open coordinates file \"" << coordsFileName
                  << "\"\n";
        return EXIT_FAILURE;
    }

    std::vector<double> vertices;
    {
        std::string line;
        while (std::getline(coordsFile, line))
        {
            if (line.empty() || line[0] == '#')
            {
                continue;
            }
            std::istringstream ss(line);
            double x, y, z;
            if (ss >> x >> y >> z)
            {
                vertices.push_back(x);
                vertices.push_back(y);
                vertices.push_back(z);
            }
        }
    }

    const int dimensions = 3;
    const int numberOfVertices =
        static_cast<int>(vertices.size()) / dimensions;

    if (numberOfVertices <= 0)
    {
        std::cerr << "DUMMY: no vertices read from \"" << coordsFileName
                  << "\"\n";
        return EXIT_FAILURE;
    }

    std::cout << "DUMMY: " << numberOfVertices << " interface vertices\n";

    precice::Participant participant(solverName, configFileName, 0, 1);

    std::vector<int> vertexIDs(numberOfVertices);
    participant.setMeshVertices(meshName, vertices, vertexIDs);

    std::vector<double> readData(numberOfVertices * dimensions, 0.0);
    std::vector<double> writeData(numberOfVertices * dimensions, 0.0);

    if (participant.requiresInitialData())
    {
        std::cout << "DUMMY: writing initial data\n";
        // Zero initial displacement: the reference configuration
        participant.writeData(meshName, writeDataName, vertexIDs, writeData);
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

        participant.readData(
            meshName, readDataName, vertexIDs, dt, readData);

        // Mock structural response: u = k * F, clamped
        double maxU = 0.0;
        for (int i = 0; i < numberOfVertices; i++)
        {
            for (int d = 0; d < dimensions; d++)
            {
                double u =
                    kSpring * readData.at(dimensions * i + d);
                u = std::max(-uMax, std::min(uMax, u));
                writeData.at(dimensions * i + d) = u;
                maxU = std::max(maxU, std::abs(u));
            }
        }

        if (step % 10 == 0)
        {
            std::cout << "DUMMY: step " << step
                      << " max|u| = " << maxU << " m\n";
        }

        participant.writeData(
            meshName, writeDataName, vertexIDs, writeData);

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
