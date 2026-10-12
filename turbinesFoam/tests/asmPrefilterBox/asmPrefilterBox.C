/*---------------------------------------------------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     |
    \\  /    A nd           | Copyright held by original author(s)
     \\/     M anipulation  |
-------------------------------------------------------------------------------
License
    This file is part of turbinesFoam, which is based on OpenFOAM.

    OpenFOAM is free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    OpenFOAM is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
    FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
    for more details.

    You should have received a copy of the GNU General Public License
    along with OpenFOAM.  If not, see <http://www.gnu.org/licenses/>.

Application
    asmPrefilterBox

Description
    Checks the cell-loop prefilter box of the actuator surface element.

    The element spreads each chord strip force with an isotropic Gaussian of
    width epsilon, truncated at projectionRadius = epsilon*sqrt(ln(1000)).
    A Gaussian is separable, so the fraction of one strip's kernel that lies
    inside an axis-aligned box is the product over the three axes of
    (erf((hi - x)/eps) + erf((x - lo)/eps))/2.

    For chords of 0.4, 1 and 3 m, at several epsilon, and for a chord that is
    skew to the axes, the check requires that
      - every strip keeps at least 99.9 % of its kernel, and
      - the box grows the chord bounding box by projectionRadius metres and
        not more (an oversized box only costs time but a different margin than
        the documented one is a defect of the same kind).

    Exits with status 1 on failure.

\*---------------------------------------------------------------------------*/

#include "argList.H"
#include "actuatorSurfaceElement.H"
#include "mathematicalConstants.H"

using namespace Foam;

// Fraction of an isotropic Gaussian of width eps centred on x that lies
// inside the box
scalar keptFraction(const boundBox& box, const point& x, const scalar eps)
{
    scalar kept = 1.0;
    for (direction d = 0; d < 3; ++d)
    {
        kept *=
            0.5
           *(
                Foam::erf((box.max()[d] - x[d])/eps)
              + Foam::erf((x[d] - box.min()[d])/eps)
            );
    }
    return kept;
}


int main(int argc, char* argv[])
{
    argList args(argc, argv);

    const scalar minKept = 0.999;
    const label nChordwise = 5;
    const scalar chords[] = {0.4, 1.0, 3.0};
    const scalar epsilons[] = {0.05, 0.2, 0.63};
    const vector directions[] = {vector(1, 0, 0), vector(1, 2, -0.5)};

    label nFail = 0;

    for (const vector& rawDir : directions)
    {
        const vector chordUnit = rawDir/mag(rawDir);

        for (const scalar chord : chords)
        {
            for (const scalar eps : epsilons)
            {
                const scalar radius =
                    eps*Foam::sqrt(Foam::log(1.0/0.001));

                const point a = 0.25*chord*chordUnit;
                const point b = -0.75*chord*chordUnit;
                const boundBox box =
                    fv::actuatorSurfaceElement::chordPrefilterBox
                    (
                        a, b, radius
                    );

                scalar worst = 1.0;
                for (label k = 0; k < nChordwise; ++k)
                {
                    const point x =
                        a + (b - a)*((k + 0.5)/nChordwise);
                    worst = min(worst, keptFraction(box, x, eps));
                }

                // Margin of the box around the bare chord bounding box
                scalar maxMargin = 0.0;
                for (direction d = 0; d < 3; ++d)
                {
                    maxMargin = max
                    (
                        maxMargin,
                        max
                        (
                            min(a[d], b[d]) - box.min()[d],
                            box.max()[d] - max(a[d], b[d])
                        )
                    );
                }

                const bool ok =
                    worst >= minKept && maxMargin <= radius*(1 + 1e-9);
                if (!ok)
                {
                    ++nFail;
                }

                Info<< (ok ? "PASS" : "FAIL")
                    << "  dir=" << rawDir << "  chord=" << chord
                    << "  eps=" << eps << "  radius=" << radius
                    << "  worstKept=" << worst
                    << "  maxMargin=" << maxMargin << endl;
            }
        }
    }

    Info<< nFail << " failing cases" << endl;
    return nFail ? 1 : 0;
}

// ************************************************************************* //
